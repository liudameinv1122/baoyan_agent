"""Offline acceptance tests for the actual HTTP routes and FFmpeg exports."""

import io
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from app.config import EXAMPLES, Settings
from app.main import create_app


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(tempfile.TemporaryDirectory(prefix="baoyan-test-"))
        self.root = Path(scratch)
        settings = Settings(data=self.root, live=False, openai_key="", fal_key="", team_password="")
        self.client = self.enterContext(TestClient(create_app(settings)))

    def post(self, path, expected=202, **kwargs):
        response = self.client.post(path, **kwargs)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def wait_for(self, path, expected):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            task = response.json()
            if task["status"] == expected:
                return task
            if task["status"] == "failed":
                self.fail(task["error"])
            time.sleep(0.1)
        self.fail(f"{path} did not reach {expected}. Last state: {task['status']}")

    def download(self, media_path, **options):
        response = self.client.get(media_path, **options)
        self.assertEqual(response.status_code, 200)
        return response.content

    def read_package(self, path, task):
        contents = self.download(f"{path}/media/materials.zip", params={"v": task["asset_version"]})
        with ZipFile(io.BytesIO(contents)) as archive:
            self.assertIsNone(archive.testzip())
            return {name: archive.read(name) for name in archive.namelist()}

    def probe(self, name, video):
        path = self.root / name
        path.write_bytes(video)
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        media = json.loads(result.stdout)
        visual = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
        self.assertEqual((visual["width"], visual["height"], visual["codec_name"]), (720, 1280, "h264"))
        self.assertTrue(any(stream["codec_type"] == "audio" for stream in media["streams"]))
        return float(media["format"]["duration"])

    def video_frame(self, name, at):
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(at), "-i", str(self.root / name),
             "-frames:v", "1", "-an", "-f", "image2pipe", "-c:v", "png", "-threads", "1", "pipe:1"],
            check=True, capture_output=True, timeout=45,
        )
        self.assertTrue(result.stdout)
        return result.stdout

    def test_promo_requires_review_and_uses_one_schedule_for_all_exports(self):
        brief = json.loads((EXAMPLES / "brief.json").read_text(encoding="utf-8"))
        task = self.post("/api/tasks/promo", json=brief)
        path = f"/api/tasks/{task['id']}"
        plan = self.wait_for(path, "review")["plan"]
        self.assertEqual(self.client.get(f"{path}/media/materials.zip").status_code, 404)
        approve = {"plan": plan, "scheduled_at": brief["scheduled_at"]}
        self.post(f"{path}/promo-review", json=approve)
        first = self.wait_for(path, "completed")
        initial = self.read_package(path, first)
        self.assertAlmostEqual(self.probe("first.mp4", initial["preview.mp4"]), 25, delta=0.18)

        date = "2026-12-05T20:00"
        self.post(f"{path}/promo-review", json=approve | {"scheduled_at": date})
        updated = self.wait_for(path, "completed")
        exported = self.read_package(path, updated)
        self.assertEqual(set(exported), {"poster.jpg", "preview.mp4", "copy.txt", "record.json"})
        self.assertNotEqual(first["asset_version"], updated["asset_version"])
        self.assertIn("19:00", initial["copy.txt"].decode())
        self.assertIn("20:00", exported["copy.txt"].decode())
        self.assertNotIn("19:00", exported["copy.txt"].decode())
        record = json.loads(exported["record.json"])
        self.assertEqual(record["mode"], "sample")
        self.assertEqual(record["schedule_display"], "2026.12.05  20:00")
        self.assertEqual(record["provider_attempts"], {})

        def date_panel(data):
            image = Image.open(io.BytesIO(data)).convert("RGB")
            return image.crop((70, 1080, 1010, 1270))

        self.assertIsNotNone(ImageChops.difference(
            date_panel(initial["poster.jpg"]), date_panel(exported["poster.jpg"])
        ).getbbox())
        self.assertAlmostEqual(self.probe("updated.mp4", exported["preview.mp4"]), 25, delta=0.18)
        self.assertEqual(self.video_frame("first.mp4", 2), self.video_frame("updated.mp4", 2))
        self.assertNotEqual(self.video_frame("first.mp4", 23), self.video_frame("updated.mp4", 23))

        older_poster = self.download(f"{path}/media/poster.jpg", params={"v": first["asset_version"]})
        self.assertEqual(older_poster, initial["poster.jpg"])
        self.assertEqual(self.download(f"{path}/media/poster.jpg"), exported["poster.jpg"])

    def test_clip_uses_uploaded_recording_and_rebases_subtitles(self):
        with (EXAMPLES / "lecture.mp4").open("rb") as video, (EXAMPLES / "lecture.srt").open("rb") as captions:
            task = self.post(
                "/api/tasks/clip",
                data={"title": "大三保研冲刺｜行动与时间节点", "audience": "parents",
                      "instruction": "重点剪家长需要关注的时间节点和提醒", "seconds": 45, "mode": "sample"},
                files={"video": ("lecture.mp4", video, "video/mp4"),
                       "srt": ("lecture.srt", captions, "application/x-subrip")},
            )
        path = f"/api/tasks/{task['id']}"
        review = self.wait_for(path, "review")
        option = review["candidates"][0]
        self.assertEqual((option["start"], option["end"]), (63.0, 100.8))
        self.assertIn("共享日历", option["quote"])
        media = self.client.get(f"{path}/media/source.mp4", headers={"Range": "bytes=0-127"})
        self.assertEqual((media.status_code, len(media.content)), (206, 128))

        request = {"candidate_id": option["id"], "start": option["start"], "end": option["end"],
                   "headline": option["headline"], "layout": "slides",
                   "copy": option["copy"], "group_copy": option["group_copy"]}
        self.post(f"{path}/clip-review", expected=422, json=request | {"end": 109.0})
        self.post(f"{path}/clip-review", json=request)
        result = self.wait_for(path, "completed")
        exported = self.read_package(path, result)
        self.assertEqual(set(exported), {"clip.mp4", "cover.jpg", "clip.srt", "copy.txt", "record.json"})
        self.assertAlmostEqual(self.probe("clip.mp4", exported["clip.mp4"]), 37.8, delta=0.15)
        clip_record = json.loads(exported["record.json"])
        self.assertEqual(clip_record["source_interval"], ["00:01:03,000", "00:01:40,800"])
        self.assertIn("共享日历", clip_record["source_quotes"][0]["text"])
        self.assertIn("00:00:00,000 -->", exported["clip.srt"].decode())
        self.assertEqual(clip_record["provider_attempts"], {})

        self.post(f"{path}/replan", json={"audience": "students", "instruction": "课程和本学期行动", "seconds": 45})
        replanned = self.wait_for(path, "review")
        self.assertNotEqual(replanned["candidates"][0]["start"], option["start"])

    def test_live_mode_requires_configuration(self):
        brief = json.loads((EXAMPLES / "brief.json").read_text(encoding="utf-8"))
        self.assertFalse(self.client.get("/api/config").json()["live_promo"])
        self.post("/api/tasks/promo", expected=409, json=brief | {"mode": "live"})
        self.assertEqual(self.client.get("/api/tasks").json(), [])


if __name__ == "__main__":
    unittest.main()
