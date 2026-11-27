import hashlib
import json
import logging
import shutil
import threading
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pydantic import ValidationError

from .config import EXAMPLES, Settings
from .media import (
    Typography, audio_for_transcription, compose_clip, compose_promo, local_date, preview_source, probe, promo_poster,
)
from .models import AUDIENCES
from .planning import Cue, WorkflowError, parse_srt, plan_clip, plan_promo, subtitles, timecode
from .providers import Providers, atomic_bytes, atomic_json
from .store import Store

LOG = logging.getLogger(__name__)
PROMO_OUTPUTS = {"preview.mp4": "预热视频", "poster.jpg": "活动海报", "copy.txt": "群文案", "record.json": "制作记录"}
CLIP_OUTPUTS = {"clip.mp4": "直播切片", "cover.jpg": "短视频封面", "clip.srt": "成片字幕",
                "copy.txt": "发布文案", "record.json": "选片记录"}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


class Workflow:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.providers = Providers(settings)
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name="media-worker", daemon=True)

    def folder(self, task_id: str) -> Path:
        return self.settings.data / "tasks" / task_id

    def run(self):
        while not self.stop.is_set():
            task = self.store.claim()
            if not task:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            try:
                if task["action"] == "plan":
                    self.plan(task)
                else:
                    self.render(task)
            except WorkflowError as exc:
                self.store.update(task["id"], status="failed", stage="处理失败", error=str(exc))
            except ValidationError:
                self.store.update(task["id"], status="failed", stage="处理失败",
                                  error="模型返回的方案字段不符合要求。请检查简报长度或重试。")
            except Exception:
                LOG.exception("Task %s failed", task["id"])
                self.store.update(task["id"], status="failed", stage="处理失败",
                                  error="任务遇到意外错误。请重试，或请管理员检查服务日志。")

    def stage(self, task, text):
        self.store.update(task["id"], stage=text)

    def call(self, task, function, label, *arguments):
        current = self.store.get(task["id"])
        counts = current.get("calls", {}).copy()
        counts[label] = counts.get(label, 0) + 1
        self.store.update(task["id"], stage=current["stage"], calls=counts)
        return function(*arguments)

    def cache_promo_plan(self, task, provider):
        work = self.folder(task["id"])
        form = task["form"]
        cached = work / "plan.json"
        if provider and cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        value = (self.call(task, plan_promo, "方案规划", form, provider) if provider
                 else plan_promo(form)).model_dump(by_alias=True)
        atomic_json(cached, value)
        return value

    def prepare_cues(self, task, work: Path, duration: float, has_audio: bool, provider) -> list[Cue]:
        recorded_srt = work / "source.srt"
        if recorded_srt.exists():
            return parse_srt(recorded_srt.read_text(encoding="utf-8-sig"), duration)
        if not has_audio or not provider:
            raise WorkflowError("请为录屏上传 SRT 字幕，或在带有音轨的录屏任务中启用实时转写。")
        self.stage(task, "提取音频并转写")
        all_cues = []
        for offset, audio in audio_for_transcription(work / "source.mp4", work, duration):
            output = work / f"asr-{offset}.srt"
            if not output.exists():
                contents = self.call(task, provider.transcribe, "语音转写", audio)
                atomic_bytes(output, contents.encode("utf-8"))
            try:
                fragment = parse_srt(output.read_text(encoding="utf-8"), min(600, duration - offset))
            except WorkflowError:
                fragment = []
            all_cues.extend(Cue(offset + cue.start, offset + cue.end, cue.text) for cue in fragment)
        if not all_cues:
            raise WorkflowError("录屏中未识别到有效语音。可以上传已有字幕。")
        # Preserve exact original cue intervals in the transcript used for editorial evidence.
        combined = "\n\n".join(
            f"{i}\n{timecode(cue.start)} --> {timecode(cue.end)}\n{cue.text}"
            for i, cue in enumerate(all_cues, 1)
        )
        atomic_bytes(recorded_srt, combined.encode("utf-8"))
        return all_cues

    def plan(self, task):
        form = task["form"]
        provider = self.providers if form["mode"] == "live" else None
        if task["kind"] == "promo":
            self.stage(task, "整理活动信息与分镜")
            plan = self.cache_promo_plan(task, provider)
            self.store.update(task["id"], status="review", stage="等待审核方案", plan=plan)
            return
        work = self.folder(task["id"])
        self.stage(task, "读取录屏和字幕")
        info = probe(work / "source.mp4")
        if info.duration > self.settings.max_source_minutes * 60:
            raise WorkflowError(f"录屏超过 {self.settings.max_source_minutes} 分钟。")
        if info.codec != "h264" and not (work / "proxy.mp4").exists():
            self.stage(task, "生成可在线播放的预览")
            preview_source(work / "source.mp4", work / "proxy-build.mp4")
            (work / "proxy-build.mp4").replace(work / "proxy.mp4")
        cues = self.prepare_cues(task, work, info.duration, info.audio, provider)
        self.stage(task, "生成候选片段")
        candidates = (self.call(task, plan_clip, "字幕选片", cues, form, provider)
                      if provider else plan_clip(cues, form))
        self.store.update(task["id"], status="review", stage="等待审核选片",
                          candidates=candidates, duration=info.duration)

    def promo_assets(self, task, work: Path, make_video: bool):
        if task["form"]["mode"] == "sample":
            return EXAMPLES / "planner.jpg", EXAMPLES / "opening.mp4", None
        plan = task["selection"]["plan"]
        media = work / "media"
        media.mkdir(exist_ok=True)
        bg = media / f"image-{digest(plan['image_prompt'])}.png"
        opening = media / f"video-{digest(plan['video_prompt'])}.mp4"
        voice = media / f"voice-{digest(plan['narration'])}.wav"
        if not bg.exists():
            self.stage(task, "生成海报背景")
            self.call(task, self.providers.image, "文生图", plan["image_prompt"], bg)
        if not make_video:
            return bg, None, None
        if not opening.exists():
            self.stage(task, "生成开场镜头")
            ticket = opening.with_suffix(".json")
            if ticket.exists():
                self.providers.video(plan["video_prompt"], opening, ticket)
            else:
                self.call(task, self.providers.video, "文生视频提交", plan["video_prompt"], opening, ticket)
        if not voice.exists():
            self.stage(task, "生成旁白")
            self.call(task, self.providers.speech, "旁白合成", plan["narration"], voice)
        return bg, opening, voice

    def render(self, task):
        work = self.folder(task["id"])
        typography = Typography(self.settings)
        revision = uuid.uuid4().hex
        output = work / "exports" / revision
        output.mkdir(parents=True)
        try:
            if task["kind"] == "promo":
                result = self.render_promo(task, work, output, typography)
                files = {file: title for file, title in PROMO_OUTPUTS.items() if file == "record.json" or (output / file).exists()}
                if (output / "narration.srt").exists():
                    files["narration.srt"] = "旁白字幕"
            else:
                result = self.render_clip(task, work, output, typography)
                files = CLIP_OUTPUTS
            self.stage(task, "打包并核对成品")
            atomic_json(output / "record.json", result["record"])
            with ZipFile(output / "materials.zip", mode="w", compression=ZIP_DEFLATED, compresslevel=3) as package:
                for file in files:
                    package.write(output / file, file)
            self.store.update(task["id"], status="completed", stage="成品可下载",
                              revision=revision, outputs=files, result=result)
        except Exception:
            shutil.rmtree(output, ignore_errors=True)
            raise

    def render_promo(self, task, work, output, typography):
        form = task["form"] | {"scheduled_at": task["selection"]["scheduled_at"]}
        plan = task["selection"]["plan"]
        needs = form.get("outputs", ["poster", "video", "copy"])
        if "poster" in needs or "video" in needs:
            bg, opening, voice = self.promo_assets(task, work, "video" in needs)
            if "poster" in needs:
                self.stage(task, "排版宣传海报")
                promo_poster(bg, output / "poster.jpg", form, plan, typography)
            if "video" in needs:
                self.stage(task, "合成预热视频")
                compose_promo(output, bg, opening, voice, form, plan, typography, EXAMPLES / "music.wav")
        schedule = local_date(form["scheduled_at"])
        copy = ""
        if "copy" in needs:
            copy = f"【{form['title']}】\n{plan['copy']}\n\n直播时间：{schedule}\n观看渠道：{form['channel']}\n"
            (output / "copy.txt").write_text(copy, encoding="utf-8")
        calls = self.store.get(task["id"]).get("calls", {})
        asset_origin = {}
        if {"poster", "video"}.intersection(needs):
            asset_origin["background"] = "本地设计样例" if form["mode"] == "sample" else "OpenAI 文生图"
        if "video" in needs:
            asset_origin["opening"] = "本地动画样例" if form["mode"] == "sample" else "fal Seedance"
            asset_origin["audio"] = "本地配乐样例" if form["mode"] == "sample" else "OpenAI 合成旁白"
        return {
            "copy": copy, "headline": plan["headline"], "scheduled_at": form["scheduled_at"],
            "record": {"mode": form["mode"], "activity": form, "approved_plan": plan,
                       "schedule_display": schedule, "provider_attempts": calls,
                       "actual_seconds": probe(output / "preview.mp4").duration if "video" in needs else None,
                       "asset_origin": asset_origin},
        }

    def render_clip(self, task, work, output, typography):
        form, selected = task["form"], task["selection"]
        source = work / "source.mp4"
        info = probe(source)
        cues = parse_srt((work / "source.srt").read_text(encoding="utf-8-sig"), info.duration)
        start, end = selected["start"], selected["end"]
        (output / "clip.srt").write_text(subtitles(cues, start, end), encoding="utf-8")
        self.stage(task, "裁切录屏并压制字幕")
        compose_clip(source, output, selected, info.audio, typography, AUDIENCES[form["audience"]])
        copy = f"视频号配文\n{selected['copy']}\n\n群文案\n{selected['group_copy']}\n"
        (output / "copy.txt").write_text(copy, encoding="utf-8")
        calls = self.store.get(task["id"]).get("calls", {})
        return {
            "copy": copy, "headline": selected["headline"], "start": start, "end": end,
            "record": {"mode": form["mode"], "request": form, "approved_cut": selected,
                       "source_interval": [timecode(start), timecode(end)],
                       "source_quotes": [{"start": cue.start, "end": cue.end, "text": cue.text}
                                         for cue in cues if cue.start < end and cue.end > start],
                       "provider_attempts": calls, "actual_seconds": probe(output / "clip.mp4").duration},
        }
