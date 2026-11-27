import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from .config import Settings
from .models import AUDIENCES
from .planning import Cue, WorkflowError, subtitles

W, H = 720, 1280
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-threads", "2", "-pix_fmt", "yuv420p",
          "-movflags", "+faststart"]


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    audio: bool
    codec: str


def run(args, cwd: Path | None = None, timeout=420) -> str:
    try:
        result = subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise WorkflowError("服务器缺少 FFmpeg 或 FFprobe，请检查安装。") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorkflowError("媒体处理超时。请尝试较短的录屏。") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else ""
        raise WorkflowError(f"媒体处理失败。{message[:180]}") from exc
    return result.stdout


def ffmpeg(*args, cwd=None, timeout=420):
    run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-filter_threads", "2", *args],
        cwd=cwd, timeout=timeout)


def probe(path: Path, *, mp4=True) -> VideoInfo:
    options = ["-f", "mov"] if mp4 else []
    body = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", *options,
                "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)],
               timeout=50)
    doc = json.loads(body)
    streams = doc.get("streams", [])
    video = next((stream for stream in streams if stream["codec_type"] == "video"), {})
    try:
        duration = float(doc["format"]["duration"])
        if not math.isfinite(duration) or duration < 0.3 or (mp4 and not video):
            raise ValueError
    except (KeyError, ValueError, TypeError) as exc:
        raise WorkflowError("无法读取录屏的有效时长和视频画面。请上传标准 MP4。") from exc
    return VideoInfo(duration, any(stream["codec_type"] == "audio" for stream in streams), video.get("codec_name", ""))


def safe_source(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file,pipe", "-f", "mov", "-i", str(path)]


def audio_for_transcription(source: Path, work: Path, duration: float):
    outputs = []
    # Small chunks stay below a single transcription upload limit even for long recordings.
    for offset in range(0, math.ceil(duration), 600):
        path = work / f"asr-{offset}.mp3"
        if not path.exists():
            ffmpeg("-ss", str(offset), *safe_source(source), "-t", str(min(600, duration - offset)),
                   "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-b:a", "40k", str(path))
        outputs.append((offset, path))
    return outputs


def preview_source(source: Path, output: Path):
    ffmpeg(*safe_source(source), "-map", "0:v:0", "-map", "0:a:0?", "-vf",
           "scale='min(960,iw)':-2", *ENCODE, "-c:a", "aac", str(output), timeout=1200)


def local_date(value: str) -> str:
    date = datetime.fromisoformat(value)
    if date.tzinfo is not None:
        date = date.astimezone(ZoneInfo("Asia/Shanghai"))
    return date.strftime("%Y.%m.%d  %H:%M")


class Typography:
    def __init__(self, settings: Settings):
        regular = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
        bold = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
        mac = Path("/System/Library/Fonts/PingFang.ttc")
        if settings.font_file:
            self.regular = self.bold = Path(settings.font_file)
            self.index = 0
        elif regular.is_file():
            self.regular, self.bold, self.index = regular, bold if bold.is_file() else regular, 2
        elif mac.is_file():
            self.regular = self.bold = mac
            self.index = 0
        else:
            raise WorkflowError("服务器需要简体中文字体。请安装 Noto Sans CJK 或设置 AGENT_CJK_FONT。")

    def font(self, size: int, bold=False):
        path = self.bold if bold else self.regular
        return ImageFont.truetype(str(path), size=size, index=self.index)

    def block(self, draw, xy, text, size, color, width, max_lines, bold=False, spacing=1.35):
        x, y = xy
        font = self.font(size, bold)
        lines = []
        line = ""
        for character in text:
            if character == "\n" or (line and draw.textlength(line + character, font=font) > width):
                lines.append(line)
                line = "" if character == "\n" else character
            else:
                line += character
        if line:
            lines.append(line)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        for line in lines:
            draw.text((x, y), line, fill=color, font=font, anchor="lt")
            y += int(size * spacing)
        return y


def visual_background(source: Path, size: tuple[int, int], strength=0.7):
    base = ImageOps.fit(Image.open(source).convert("RGB"), size)
    base = ImageEnhance.Brightness(base).enhance(strength)
    wash = Image.new("RGBA", size)
    draw = ImageDraw.Draw(wash)
    for y in range(size[1]):
        alpha = int(60 + 165 * (y / size[1]) ** 1.15)
        draw.line((0, y, size[0], y), fill=(8, 28, 32, alpha))
    return Image.alpha_composite(base.convert("RGBA"), wash).convert("RGB")


def promo_poster(background: Path, dst: Path, form: dict, plan: dict, typography: Typography):
    image = visual_background(background, (1080, 1350), 0.82)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 74, 326, 143), radius=33, fill="#d1ec8c")
    draw.text((99, 108), "保研冲刺 · 直播预告", font=typography.font(26, True), fill="#1c342e", anchor="lm")
    draw.text((75, 355), "GRADUATE ADMISSIONS", font=typography.font(25), fill="#cae4bb", anchor="lt")
    bottom = typography.block(draw, (71, 420), plan["headline"], 96, "#ffffff", 930, 3, bold=True)
    draw.line((75, bottom + 24, 990, bottom + 24), fill="#91b49a", width=2)
    draw.text((75, bottom + 63), f"面向{AUDIENCES[form['audience']]}", font=typography.font(34), fill="#e2f0d9", anchor="lt")
    draw.rounded_rectangle((70, 1070, 1010, 1268), radius=30, fill="#e3f2c9")
    draw.text((107, 1110), "直播时间", font=typography.font(29, True), fill="#315047", anchor="lt")
    draw.text((107, 1173), local_date(form["scheduled_at"]), font=typography.font(49, True), fill="#102c25", anchor="lt")
    typography.block(draw, (695, 1125), form["channel"], 27, "#315047", 260, 2, bold=True)
    image.save(dst, quality=92, optimize=True)


def promo_card(dst: Path, *, typography: Typography, image: Path, label: str, title: str, detail="", tail=False):
    card = visual_background(image, (W, H), 0.62)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((50, 60, 670, 1220), radius=32, outline="#759387", width=2)
    typography.block(draw, (82, 114), label, 26, "#d3ed94", 555, 1, bold=True)
    if tail:
        y = typography.block(draw, (80, 467), title, 55, "#ffffff", 560, 3, bold=True)
        draw.rounded_rectangle((80, y + 65, 640, y + 175), radius=23, fill="#d3ed94")
        typography.block(draw, (101, y + 98), detail, 32, "#1a3d31", 510, 1, bold=True)
    else:
        y = typography.block(draw, (82, 380), title, 56, "#ffffff", 550, 5, bold=True)
        if detail:
            typography.block(draw, (84, y + 70), detail, 27, "#d5ead9", 545, 2)
    card.save(dst, quality=90)


def clip_cover(frame: Path, dst: Path, typography: Typography, headline: str, audience: str, interval: str):
    base = Image.new("RGB", (W, H), "#172e36")
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((49, 73, 250, 132), radius=28, fill="#d9edaa")
    draw.text((73, 102), "保研直播回放", fill="#1b3936", font=typography.font(24, True), anchor="lm")
    typography.block(draw, (50, 212), headline, 64, "#ffffff", 620, 4, bold=True)
    picture = ImageOps.contain(Image.open(frame).convert("RGB"), (620, 435))
    base.paste(picture, ((W - picture.width) // 2, 650 + (435 - picture.height) // 2))
    draw = ImageDraw.Draw(base)
    draw.line((50, 1114, 670, 1114), fill="#809e99", width=1)
    draw.text((51, 1150), f"{audience}  /  {interval}", font=typography.font(25), fill="#cfdfda", anchor="lt")
    base.save(dst, quality=92, optimize=True)


def still_video(src: Path, dst: Path, seconds: float):
    ffmpeg("-loop", "1", "-framerate", "25", "-i", str(src), "-t", str(seconds),
           "-an", "-vf", "setsar=1,format=yuv420p", *ENCODE, str(dst))


def audio_mix(timeline: Path, dst: Path, duration: float, audio: Path, narration: str | None = None):
    common = ["-i", str(timeline)]
    audio_length = probe(audio, mp4=False).duration
    tempo = max(1, min(8, audio_length / (duration - 0.4))) if narration else 1
    factor = tempo
    chain = []
    while factor > 2:
        chain.append("atempo=2")
        factor /= 2
    chain.append(f"atempo={factor}")
    chain.append("apad")
    audio_args = ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                  "-af", ",".join(chain), "-c:a", "aac", "-b:a", "128k"]
    video_args = ["-c:v", "copy", "-movflags", "+faststart"]
    if narration:
        # TTS returns audio rather than word timings. Use punctuation-sized caption cues
        # distributed across the measured narration duration.
        chunks = [item.strip() for item in re.split(r"(?<=[。！？；，、])", narration) if item.strip()]
        total = sum(len(item) for item in chunks)
        end = 0.0
        cues = []
        for text in chunks:
            start, end = end, end + min(duration, audio_length / tempo) * len(text) / total
            cues.append(Cue(start, end, text))
        subtitle = dst.parent / "narration.srt"
        subtitle.write_text(subtitles(cues), encoding="utf-8")
        video_args = ["-vf", subtitle_filter(subtitle.name), *ENCODE]
    ffmpeg(*common, *audio_args, *video_args, "-t", str(duration), str(dst), cwd=dst.parent)


def subtitle_filter(name: str):
    return (
        f"subtitles={name}:force_style='FontName=Noto Sans CJK SC,FontSize=11,Alignment=2,"
        "MarginV=26,MarginL=19,MarginR=19,Outline=1.7,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101416'"
    )


def compose_promo(output: Path, bg: Path, opening: Path, voice: Path | None, form: dict, plan: dict, typography: Typography, music: Path):
    duration = form["seconds"]
    first, tail = 4, 4
    count = len(plan["points"])
    durations = [round((duration - first - tail) / count, 2)] * count
    durations[-1] = round(duration - first - tail - sum(durations[:-1]), 2)
    segments = [output / "segment-0.mp4"]
    ffmpeg(*safe_source(opening), "-t", str(first), "-an",
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                  "fps=25,tpad=stop_mode=clone:stop_duration=4",
           *ENCODE, str(segments[0]))
    for index, (point, seconds) in enumerate(zip(plan["points"], durations), 1):
        still = output / f"card-{index}.jpg"
        promo_card(still, typography=typography, image=bg, label=f"{index:02d}   直播议题",
                   title=point, detail=f"{form['title']}  ·  {AUDIENCES[form['audience']]}")
        segment = output / f"segment-{index}.mp4"
        still_video(still, segment, seconds)
        segments.append(segment)
    endcard = output / "card-last.jpg"
    promo_card(endcard, typography=typography, image=bg, label=f"直播预告  /  {form['channel']}",
               title=form["title"], detail=local_date(form["scheduled_at"]), tail=True)
    end_segment = output / "segment-last.mp4"
    still_video(endcard, end_segment, tail)
    segments.append(end_segment)
    listing = output / "timeline.txt"
    listing.write_text("".join(f"file '{segment.name}'\n" for segment in segments), encoding="utf-8")
    timeline = output / "timeline.mp4"
    ffmpeg("-f", "concat", "-safe", "1", "-i", str(listing), "-c", "copy", str(timeline), cwd=output)
    audio_mix(timeline, output / "preview.mp4", duration, voice or music, plan["narration"] if voice else None)
    for item in [*segments, *output.glob("card-*.jpg"), listing, timeline]:
        item.unlink()


def compose_clip(source: Path, output: Path, review: dict, has_audio: bool, typography: Typography, audience: str):
    start, end = review["start"], review["end"]
    frame = output / "source-frame.jpg"
    ffmpeg("-ss", str(start + min(0.3, (end - start) / 3)), *safe_source(source), "-frames:v", "1", str(frame))
    interval = f"{int(start // 60):02d}:{int(start % 60):02d} – {int(end // 60):02d}:{int(end % 60):02d}"
    clip_cover(frame, output / "cover.jpg", typography, review["headline"], audience, interval)
    frame.unlink()
    if review["layout"] == "speaker":
        framing = f"scale={W}:{H}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={W}:{H}"
    else:
        framing = (
            f"scale={W - 36}:{H - 320}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x172e36"
        )
    filters = f"{framing},setsar=1,fps=25"
    if (output / "clip.srt").stat().st_size > 5:
        filters += "," + subtitle_filter("clip.srt")
    audio = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"] if has_audio else ["-an"]
    ffmpeg("-ss", f"{start:.3f}", *safe_source(source), "-t", f"{end - start:.3f}",
           "-map", "0:v:0", *audio, "-vf", filters, *ENCODE, str(output / "clip.mp4"), cwd=output)
