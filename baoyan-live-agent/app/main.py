import base64
import binascii
import fcntl
import secrets
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import EXAMPLES, ROOT, Settings
from .models import ClipReplan, ClipRequest, ClipReview, Promo, PromoReview
from .planning import WorkflowError
from .store import Store
from .workflow import CLIP_OUTPUTS, PROMO_OUTPUTS, Workflow

UI = ROOT / "ui" / "dist"


def public_task(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "revision"} | {"asset_version": task.get("revision")}


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    store = Store(settings.data / "tasks.sqlite3")
    engine = Workflow(settings, store)

    @asynccontextmanager
    async def lifespan(_app):
        store.initialize()
        with (settings.data / "worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("同一数据目录已启动一个工作台服务。") from exc
            store.recover()
            engine.thread.start()
            try:
                yield
            finally:
                engine.stop.set()
                engine.wake.set()
                engine.thread.join(timeout=2)

    app = FastAPI(title="保研内容工作台", version="1.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def team_access(request: Request, call_next):
        if settings.team_password:
            scheme, _, value = request.headers.get("Authorization", "").partition(" ")
            try:
                expected = f"{settings.team_user}:{settings.team_password}".encode()
                valid = scheme.lower() == "basic" and secrets.compare_digest(base64.b64decode(value, validate=True), expected)
            except (ValueError, binascii.Error):
                valid = False
            if not valid:
                return PlainTextResponse("请输入团队账号和访问密码。", 401, {"WWW-Authenticate": 'Basic realm="Content Studio"'})
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            cross_site = request.headers.get("sec-fetch-site") == "cross-site"
            if cross_site or (origin and urlparse(origin).netloc != request.headers.get("host")):
                return JSONResponse({"detail": "请在工作台页面内提交任务。"}, 403)
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > (settings.max_upload_mb + 4) * 1024 * 1024:
                return JSONResponse({"detail": f"上传总大小超过 {settings.max_upload_mb} MB。"}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        fields = "、".join(dict.fromkeys(str(item["loc"][-1]) for item in exc.errors()[:5]))
        return JSONResponse({"detail": f"请检查这些字段的填写内容或长度：{fields}。"}, 422)

    def get_task(task_id: UUID):
        task = store.get(str(task_id))
        if task is None:
            raise HTTPException(404, "找不到这个任务。")
        return task

    def check_mode(kind, mode, outputs=("poster", "video", "copy")):
        if mode == "live" and not (settings.live_promo if kind == "promo" else settings.live_editor):
            raise HTTPException(409, "管理员尚未配置该流程的实时 API。请选择样例模式。")
        if kind == "promo" and mode == "live" and "video" in outputs and not settings.live_video:
            raise HTTPException(409, "管理员尚未配置实时视频生成。可以先选择海报或文案，或切换样例模式。")

    def requeue(task, action, allowed, changes):
        check_mode(task["kind"], task["form"]["mode"], task["form"].get("outputs", ("poster", "video", "copy")))
        if not store.enqueue(task["id"], action, allowed, changes):
            raise HTTPException(409, "这个任务正在处理，或当前状态无法提交。")
        engine.wake.set()
        return public_task(store.get(task["id"]))

    @app.get("/api/config")
    def config():
        return {"live_promo": settings.live_promo, "live_video": settings.live_video, "live_clip": settings.live_editor,
                "sample_clip": (EXAMPLES / "lecture.mp4").is_file(),
                "max_upload_mb": settings.max_upload_mb, "max_source_minutes": settings.max_source_minutes,
                "team_access": bool(settings.team_password)}

    @app.get("/api/tasks")
    def list_tasks():
        keys = ("id", "kind", "status", "stage", "created_at", "updated_at")
        return [{key: task[key] for key in keys} | {
            "title": task["form"]["title"], "audience": task["form"]["audience"], "mode": task["form"]["mode"]
        } for task in store.list()]

    @app.get("/api/tasks/{task_id}")
    def task_detail(task_id: UUID):
        return public_task(get_task(task_id))

    @app.post("/api/tasks/promo", status_code=202)
    def create_promo(form: Promo):
        check_mode("promo", form.mode, form.outputs)
        task = store.create(str(uuid.uuid4()), "promo", form.model_dump(mode="json"))
        engine.wake.set()
        return public_task(task)

    async def save_upload(upload: UploadFile, path: Path, limit: int):
        length = 0
        with path.open("wb") as stream:
            while data := await upload.read(1024 * 1024):
                length += len(data)
                if length > limit:
                    raise HTTPException(413, f"文件超出 {limit // (1024 * 1024)} MB 的上传限制。")
                stream.write(data)
        if not length:
            raise HTTPException(422, "上传文件为空。")

    @app.post("/api/tasks/clip", status_code=202)
    async def create_clip(
        title: str = Form(...), audience: str = Form("parents"), instruction: str = Form(""),
        seconds: int = Form(45), mode: str = Form("sample"), use_example: bool = Form(False),
        video: UploadFile | None = File(None), srt: UploadFile | None = File(None),
    ):
        try:
            form = ClipRequest(title=title, audience=audience, instruction=instruction, seconds=seconds, mode=mode)
        except ValidationError as exc:
            raise HTTPException(422, "请检查录屏任务的标题、受众或时长（10–60 秒）。") from exc
        check_mode("clip", form.mode)
        if not use_example and (video is None or Path(video.filename or "").suffix.lower() != ".mp4"):
            raise HTTPException(422, "请上传 MP4 格式的直播录屏。")
        if not use_example and srt is None and mode != "live":
            raise HTTPException(422, "样例模式下，自有录屏需一并上传 SRT 字幕。")
        if srt is not None and Path(srt.filename or "").suffix.lower() != ".srt":
            raise HTTPException(422, "请上传 SRT 格式的字幕。")
        task_id = str(uuid.uuid4())
        folder = engine.folder(task_id)
        folder.mkdir(parents=True)
        try:
            if use_example:
                shutil.copyfile(EXAMPLES / "lecture.mp4", folder / "source.mp4")
                shutil.copyfile(EXAMPLES / "lecture.srt", folder / "source.srt")
            else:
                await save_upload(video, folder / "source.mp4", settings.max_upload_mb * 1024 * 1024)
                if srt is not None:
                    await save_upload(srt, folder / "source.srt", 4 * 1024 * 1024)
                    try:
                        (folder / "source.srt").read_text(encoding="utf-8-sig")
                    except UnicodeDecodeError as exc:
                        raise HTTPException(422, "请先将 SRT 字幕保存为 UTF-8。") from exc
            task = store.create(task_id, "clip", form.model_dump(mode="json"))
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        engine.wake.set()
        return public_task(task)

    @app.post("/api/tasks/{task_id}/promo-review", status_code=202)
    def review_promo(task_id: UUID, review: PromoReview):
        task = get_task(task_id)
        if task["kind"] != "promo" or not task.get("plan"):
            raise HTTPException(409, "这个任务还没有可审核的预热方案。")
        return requeue(task, "render", ("review", "completed", "failed"),
                       {"selection": review.model_dump(mode="json", by_alias=True)})

    @app.post("/api/tasks/{task_id}/clip-review", status_code=202)
    def review_clip(task_id: UUID, review: ClipReview):
        task = get_task(task_id)
        ids = {candidate["id"] for candidate in task.get("candidates", [])}
        if task["kind"] != "clip" or review.candidate_id not in ids:
            raise HTTPException(409, "请先选择一条当前推荐的片段。")
        form = task["form"]
        if not (0.5 <= review.end - review.start <= form["seconds"] + 0.001
                and review.end <= task["duration"] + 0.0005):
            raise HTTPException(422, f"切点须位于录屏内，片段时长为 0.5 至 {form['seconds']} 秒。")
        return requeue(task, "render", ("review", "completed", "failed"),
                       {"selection": review.model_dump(mode="json", by_alias=True)})

    @app.post("/api/tasks/{task_id}/replan", status_code=202)
    def replan_clip(task_id: UUID, form: ClipReplan):
        task = get_task(task_id)
        if task["kind"] != "clip":
            raise HTTPException(409, "只有录屏任务可以重新选片。")
        return requeue(task, "plan", ("review", "completed", "failed"),
                       {"form": task["form"] | form.model_dump(), "candidates": [], "selection": None})

    @app.post("/api/tasks/{task_id}/retry", status_code=202)
    def retry(task_id: UUID):
        task = get_task(task_id)
        return requeue(task, task["action"], ("failed",), {})

    @app.get("/api/tasks/{task_id}/media/{name}")
    def media(task_id: UUID, name: str, download: bool = False, v: UUID | None = None):
        task = get_task(task_id)
        work = engine.folder(str(task_id))
        allowed = CLIP_OUTPUTS if task["kind"] == "clip" else PROMO_OUTPUTS | {"narration.srt": "旁白字幕"}
        version = v.hex if v else task.get("revision")
        if name == "source.mp4" and task["kind"] == "clip":
            proxy = work / "proxy.mp4"
            path = (proxy if proxy.exists() and not download else work / "source.mp4")
        elif version and task.get("revision") and (name == "materials.zip" or name in allowed):
            path = work / "exports" / version / name
        else:
            raise HTTPException(404, "没有找到这份素材。")
        if not path.is_file():
            raise HTTPException(404, "素材文件不存在。")
        return FileResponse(path, filename=name, content_disposition_type="attachment" if download else "inline")

    if (UI / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=UI / "assets"), name="ui-assets")

    @app.get("/")
    def index():
        if (UI / "index.html").is_file():
            return FileResponse(UI / "index.html")
        return PlainTextResponse("前端尚未构建。请在 ui 目录运行 npm ci 和 npm run build，再重启服务。", 503)

    return app


app = create_app()
