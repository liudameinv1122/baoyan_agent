"""The paid-video retry uses a saved request ID and performs no real calls here."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import EXAMPLES, Settings
from app.planning import WorkflowError
from app.providers import FAL_ENDPOINT, Providers


class VideoProviderRetryTest(unittest.TestCase):
    def test_does_not_resubmit_after_status_request_fails(self):
        remote = "https://queue.fal.run/bytedance/seedance-2.0/requests/test-job"
        video_bytes = (EXAMPLES / "opening.mp4").read_bytes()
        calls = []

        def respond(request):
            url = str(request.url)
            calls.append((request.method, url))
            if url == FAL_ENDPOINT:
                self.assertEqual(request.method, "POST")
                self.assertEqual(json.loads(request.content)["aspect_ratio"], "9:16")
                return httpx.Response(200, json={
                    "request_id": "test-job", "status_url": f"{remote}/status", "response_url": remote,
                })
            if url == f"{remote}/status":
                if calls.count(("GET", url)) == 1:
                    return httpx.Response(503)
                return httpx.Response(200, json={"status": "COMPLETED"})
            if url == remote:
                return httpx.Response(200, json={"video": {"url": "https://v3.fal.media/test.mp4"}})
            if url == "https://v3.fal.media/test.mp4":
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, content=video_bytes)
            self.fail(f"Unexpected provider request: {request.method} {url}")

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        output, ticket = directory / "test.mp4", directory / "test.json"
        provider = Providers(Settings(data=directory, fal_key="local-test-only"))
        transport = httpx.MockTransport(respond)
        client = httpx.Client

        with patch("app.providers.httpx.Client", side_effect=lambda **kwargs: client(transport=transport, **kwargs)):
            with self.assertRaisesRegex(WorkflowError, "HTTP 503"):
                provider.video("Example", output, ticket)
            self.assertEqual(json.loads(ticket.read_text())["request_id"], "test-job")
            self.assertFalse(output.exists())
            provider.video("Example", output, ticket)

        self.assertEqual(calls.count(("POST", FAL_ENDPOINT)), 1)
        self.assertEqual(output.read_bytes(), video_bytes)


if __name__ == "__main__":
    unittest.main()
