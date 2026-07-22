from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.control_station import ControlStationService


class ControlStationTests(unittest.TestCase):
    def test_reads_write_access_status(self) -> None:
        payload = {
            "state": [
                {
                    "_type": "controlstation-write-access-status",
                    "held-by-control-station-Id": "none",
                    "held-by-control-station-name": "none",
                    "control-station-write-access-held": "false",
                    "control-station-external-control-enabled": "true",
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(
                request.url.path, "/rw/controlstation/writeaccess/status"
            )
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            status = ControlStationService(client).status()

        self.assertFalse(status.held)
        self.assertTrue(status.external_control_enabled)
        self.assertEqual(status.holder_name, "none")


if __name__ == "__main__":
    unittest.main()
