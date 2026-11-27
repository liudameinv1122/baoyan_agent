import base64
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import Settings
from .planning import WorkflowError

FAL_ENDPOINT = "https://queue.fal.run/bytedance/seedance-2.0/fast/text-to-video"


def atomic_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def atomic_json(path: Path, fields: dict):
    atomic_bytes(path, json.dumps(fields, ensure_ascii=False, indent=2).encode("utf-8"))


class Providers:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def check(response: httpx.Response, label: str):
        if response.is_success:
            return response
        explanations = {
            400: "参数或输入被服务拒绝",
            401: "密钥无效",
            402: "请检查账户余额",
            403: "请检查模型权限",
            404: "请检查模型或地址",
            413: "输入文件超出供应商限制",
            429: "额度或速率已达上限",
        }
        reason = explanations.get(response.status_code, "服务暂时不可用")
        raise WorkflowError(f"{label}调用失败（HTTP {response.status_code}）。{reason}。")

    def openai(self, endpoint: str, label: str, **kwargs) -> httpx.Response:
        try:
            response = httpx.post(
                f"{self.settings.openai_base}/{endpoint}",
                headers={"Authorization": f"Bearer {self.settings.openai_key}"},
                timeout=httpx.Timeout(240, connect=15),
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise WorkflowError(f"{label}服务连接中断，无法确认远端是否完成。请先核对服务的调用记录。") from exc
        return self.check(response, label)

    def json(self, system: str, user: str) -> dict:
        response = self.openai("chat/completions", "文案与选片模型", json={
            "model": self.settings.text_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        })
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if isinstance(data, dict):
                return data
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        raise WorkflowError("文案与选片模型的响应缺少可用的 JSON。可以换用支持 JSON 输出的模型。")

    def transcribe(self, source: Path) -> str:
        with source.open("rb") as stream:
            response = self.openai(
                "audio/transcriptions", "语音转写",
                files={"file": (source.name, stream, "audio/mpeg")},
                data={"model": "whisper-1", "response_format": "srt", "language": "zh"},
            )
        return response.text

    def speech(self, narration: str, output: Path):
        response = self.openai("audio/speech", "旁白", json={
            "model": self.settings.speech_model,
            "voice": self.settings.speech_voice,
            "input": narration,
            "response_format": "wav",
        })
        atomic_bytes(output, response.content)

    def image(self, prompt: str, output: Path):
        response = self.openai("images/generations", "文生图", json={
            "model": self.settings.image_model, "prompt": prompt,
            "size": "1024x1536", "quality": "medium", "n": 1, "output_format": "png",
        })
        try:
            encoded = response.json()["data"][0]["b64_json"]
            image = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise WorkflowError("文生图服务返回了无法读取的 PNG。请检查模型配置。") from exc
        atomic_bytes(output, image)

    def video(self, prompt: str, output: Path, ticket: Path):
        headers = {"Authorization": f"Key {self.settings.fal_key}"}
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=15)) as client:
                if ticket.exists():
                    job = json.loads(ticket.read_text(encoding="utf-8"))
                    if not job.get("request_id"):
                        raise WorkflowError("上次视频生成的提交状态未知。请先在 fal 后台核对调用记录。")
                else:
                    atomic_json(ticket, {"state": "submitting"})
                    response = client.post(FAL_ENDPOINT, headers=headers, json={
                        "prompt": prompt, "duration": "4", "resolution": "720p",
                        "aspect_ratio": "9:16", "generate_audio": False,
                    })
                    if response.status_code in (400, 401, 402, 403, 404, 422, 429):
                        ticket.unlink(missing_ok=True)
                    self.check(response, "文生视频")
                    job = response.json()
                    atomic_json(ticket, job)
                status_url = self.queue_url(job.get("status_url"))
                response_url = self.queue_url(job.get("response_url"))
                wait_until = time.monotonic() + 300
                while time.monotonic() < wait_until:
                    status = self.check(client.get(status_url, headers=headers), "视频任务查询").json()
                    if status.get("status") == "COMPLETED":
                        break
                    if status.get("status") not in ("IN_QUEUE", "IN_PROGRESS"):
                        raise WorkflowError("视频任务状态异常，请核对 fal 控制台。")
                    time.sleep(3)
                else:
                    raise WorkflowError("视频仍在生成。点击重试会继续查询同一任务。")
                result = self.check(client.get(response_url, headers=headers), "视频结果").json()
                video_url = result.get("video", {}).get("url", "")
                cdn = urlparse(video_url)
                if (cdn.scheme != "https" or not cdn.hostname
                        or (cdn.hostname != "fal.media" and not cdn.hostname.endswith(".fal.media"))):
                    raise WorkflowError("视频服务返回了无法识别的素材地址。")
                with client.stream("GET", video_url) as download:
                    self.check(download, "视频下载")
                    partial = output.with_suffix(".mp4.part")
                    size = 0
                    with partial.open("wb") as stream:
                        for chunk in download.iter_bytes():
                            size += len(chunk)
                            if size > 100 * 1024 * 1024:
                                raise WorkflowError("开场镜头文件超过 100 MB。")
                            stream.write(chunk)
                    partial.replace(output)
        except httpx.RequestError as exc:
            raise WorkflowError("视频服务连接中断。已有任务编号时，重试会继续查询该任务。") from exc

    @staticmethod
    def queue_url(value):
        if not isinstance(value, str) or urlparse(value).netloc != "queue.fal.run" or not value.startswith("https://"):
            raise WorkflowError("视频服务未返回有效的任务查询地址。")
        return value
