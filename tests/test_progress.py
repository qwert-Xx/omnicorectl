from __future__ import annotations

import unittest

import httpx

from omnicorectl.errors import ProtocolError
from omnicorectl.rws import RwsClient
from omnicorectl.rws.progress import ProgressService


class ProgressTests(unittest.TestCase):
    def test_pending_progress_stops_at_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                json={"state": [{"state": "pending", "code": "0"}]},
            )

        clock_values = iter((0.0, 1.0))
        sleeps: list[float] = []
        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            progress = ProgressService(
                client,
                clock=lambda: next(clock_values),
                sleep=sleeps.append,
            )
            with self.assertRaisesRegex(ProtocolError, "did not complete"):
                progress.wait(
                    "/progress/1",
                    timeout=0.5,
                    poll_interval=0.1,
                )

        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
