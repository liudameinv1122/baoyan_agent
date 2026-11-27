"""Build original sample media. Requires FFmpeg and a Chinese font."""
import argparse
import json
import math
import random
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import EXAMPLES, Settings
from app.media import ENCODE, Typography, ffmpeg, probe, promo_poster
from app.planning import local_promo, timecode

PROMO = {
    "title": "大三保研冲刺直播", "audience": "students", "scheduled_at": "2026-12-05T19:00",
    "channel": "视频号直播",
    "brief": "用三个问题盘点课程成绩与科研经历\n规划寒假前的行动事项和时间节点\n直播集中答疑，整理材料准备清单",
    "seconds": 25, "mode": "sample",
}

LESSON = [
    ("大三保研冲刺", "先盘点，再行动", "今天我们分两部分讲。先讲大三学生这学期能做什么，再讲家长应该关注哪些时间节点。"),
    ("学生的行动计划", "盘点基础与目标", "同学们先把最近的成绩单和课程安排打开，写下当前情况，再确认这学期最需要补齐的一项。"),
    ("学生的行动计划", "把任务排进日历", "学生可以把课程复习、科研实践和材料整理分开，先给每项设一个本周能完成的结果。"),
    ("学生的行动计划", "留下可以复盘的记录", "科研经历可以按问题、做法和结果做记录，周末回看时再补上证据和下一步行动。"),
    ("家长关心的三个节点", "留意学校发布通知", "家长可以先和孩子一起看学校正式通知。重点是信息更新、材料提交和结果确认这三个时间节点。"),
    ("家长关心的三个节点", "提前确认材料与提醒", "家长能提供的帮助是把时间节点记进共享日历，提醒孩子提前留出核对材料的时间。"),
    ("家长关心的三个节点", "用确认代替催促", "到了材料提交的节点，可以先问孩子核对到哪一步，再给需要的支持，比如帮忙检查文件是否齐全。"),
    ("家长关心的三个节点", "保留孩子的决策空间", "家长做好提醒和陪伴，具体选择和对外沟通交给孩子。院校日期以当年的正式通知为准。"),
    ("直播问答", "把问题记到自己的清单", "最后请大家写下一件本周马上就能完成的事。下次复盘时先看这条是否做到，再调整下一步计划。"),
]


def notebook(path):
    random.seed(18)
    image = Image.new("RGB", (900, 1350))
    pixels = []
    for y in range(1350):
        for x in range(900):
            light = max(0, 1 - math.hypot(0.93 * x - 605, y - 251) / 880)
            grain = random.choice((-3, -2, -1, 0, 1, 2, 3))
            pixels.append((max(0, int(15 + 65 * light + grain)),
                           int(46 + 61 * light + grain), int(38 + 42 * light + grain)))
    image.putdata(pixels)
    image = image.convert("RGBA")
    book = Image.new("RGBA", (590, 630))
    draw = ImageDraw.Draw(book)
    draw.rounded_rectangle((18, 16, 570, 618), radius=19, fill="#63855f")
    draw.rounded_rectangle((24, 9, 567, 602), radius=17, fill="#b6b49b")
    draw.rounded_rectangle((32, 3, 562, 590), radius=13, fill="#e9dfc4")
    draw.line((298, 10, 298, 583), fill="#a8a38e", width=2)
    for row in range(70, 565, 29):
        draw.line((53, row, 275, row), fill="#cdcab4", width=2)
        draw.line((319, row, 538, row), fill="#cdcab4", width=2)
    for x in range(358, 540, 25):
        draw.line((x, 70, x, 280), fill="#d7d1b7", width=1)
    draw.rounded_rectangle((399, 150, 478, 216), radius=4, fill="#c3cda1")
    draw.rounded_rectangle((144, 233, 236, 273), radius=4, fill="#c8cfab")
    book = book.rotate(-23, resample=Image.Resampling.BICUBIC, expand=True)
    shadow = Image.new("RGBA", book.size, "#092a24")
    shadow.putalpha(book.getchannel("A").point(lambda a: int(a * 0.7)))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(25)), (306, 94))
    image.alpha_composite(book, (283, 72))
    draw = ImageDraw.Draw(image)
    draw.line((541, 798, 826, 572), fill="#203a35", width=17)
    draw.line((536, 790, 821, 564), fill="#abc180", width=12)
    draw.line((537, 786, 821, 560), fill="#d5dfaf", width=3)
    draw.polygon([(536, 784), (544, 793), (519, 803)], fill="#d4c3a0")
    image.convert("RGB").save(path, quality=93)


def music(path):
    sample_rate = 16000
    notes = (220, 261.63, 329.63, 392.00, 293.66, 246.94, 329.63, 440)
    samples = array("h")
    for i in range(sample_rate * 34):
        moment = i / sample_rate
        t = moment % 1.65
        frequency = notes[int(moment / 1.65) % len(notes)]
        amp = min(t / 0.09, 1) * math.exp(-2.3 * t)
        tone = math.sin(math.tau * frequency * t) + 0.21 * math.sin(math.tau * frequency * 2 * t)
        tone *= min(1, (34 - moment) / 1.2)
        samples.append(int(tone * amp * 1350))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())


def slide(dst, title, point, typography, column):
    image = Image.new("RGB", (1280, 720), "#183c32")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((47, 47, 1230, 670), radius=27, fill="#f0f3e8")
    draw.rounded_rectangle((89, 93, 301, 146), radius=24, fill="#d9eba8")
    draw.text((110, 118), "保研冲刺 · 讲座示例", fill="#244335", font=typography.font(21, True), anchor="lm")
    typography.block(draw, (90, 255), title, 69, "#183c32", 900, 2, bold=True)
    typography.block(draw, (92, 376), point, 37, "#436652", 960, 2)
    draw.line((91, 500, 1188, 500), fill="#a6b8a8", width=2)
    labels = ("盘点现状", "制定本周行动", "检查时间节点")
    for i, label in enumerate(labels):
        x = 93 + i * 360
        draw.rounded_rectangle((x, 543, x + 326, 613), radius=12,
                               fill="#275849" if i == column else "#e4ecdc")
        draw.text((x + 23, 577), label, fill="#ebf5db" if i == column else "#406653",
                  font=typography.font(26, True), anchor="lm")
    image.save(dst, quality=89)


def make_recording(work, typography, voice_package):
    words = work / "words.json"
    words.write_text(json.dumps([item[2] for item in LESSON], ensure_ascii=False), encoding="utf-8")
    if voice_package:
        subprocess.run(["node", str(ROOT / "scripts/synth_example.mjs"), str(voice_package),
                        str(words), str(work)], check=True)
    intervals = []
    files = []
    start = 0.0
    for i, (title, point, sentence) in enumerate(LESSON):
        still = work / f"slide-{i}.jpg"
        slide(still, title, point, typography, 0 if i < 2 else 1 if i < 4 else 2)
        voice = work / f"speech-{i}.wav"
        if voice.is_file():
            seconds = math.ceil(probe(voice, mp4=False).duration + 0.4)
            audio = ["-i", str(voice), "-af", "apad", "-c:a", "aac", "-ar", "32000"]
        else:
            seconds = 8
            audio = ["-an"]
        segment = work / f"lesson-{i}.mp4"
        ffmpeg("-loop", "1", "-framerate", "25", "-i", str(still), *audio, "-t", str(seconds),
               "-vf", "setsar=1,format=yuv420p", *ENCODE, str(segment))
        files.append(segment)
        intervals.append(f"{i + 1}\n{timecode(start)} --> {timecode(start + seconds - 0.2)}\n{sentence}")
        start += seconds
    manifest = work / "lesson.txt"
    manifest.write_text("".join(f"file '{item.name}'\n" for item in files), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "1", "-i", str(manifest), "-c", "copy",
           "-movflags", "+faststart", str(EXAMPLES / "lecture.mp4"), cwd=work)
    (EXAMPLES / "lecture.srt").write_text("\n\n".join(intervals) + "\n", encoding="utf-8")
    return work / "slide-4.jpg"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-package", type=Path, help="Optional espeak-ng@1.0.2 package directory")
    args = parser.parse_args()
    EXAMPLES.mkdir(exist_ok=True)
    web_assets = ROOT / "ui" / "public" / "assets"
    web_assets.mkdir(parents=True, exist_ok=True)
    typography = Typography(Settings())
    with tempfile.TemporaryDirectory(prefix="baoyan-example-") as temporary:
        work = Path(temporary)
        notebook(EXAMPLES / "planner.jpg")
        music(EXAMPLES / "music.wav")
        ffmpeg("-i", str(EXAMPLES / "planner.jpg"),
               "-vf", "scale=1200:1800,zoompan=z='1+on*0.0016':x='iw*0.58-iw/zoom*0.5':"
                      "y='ih*0.47-ih/zoom*0.45':d=100:s=720x1280:fps=25",
               "-an", "-t", "4", *ENCODE, str(EXAMPLES / "opening.mp4"))
        example_slide = make_recording(work, typography, args.voice_package)
        Image.open(example_slide).resize((680, 382)).save(web_assets / "studio-slide.webp", quality=88)
        poster = work / "poster.jpg"
        promo_poster(EXAMPLES / "planner.jpg", poster, PROMO, local_promo(PROMO).model_dump(by_alias=True), typography)
        Image.open(poster).resize((420, 525)).save(web_assets / "studio-poster.webp", quality=92)
    (EXAMPLES / "brief.json").write_text(json.dumps(PROMO, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
