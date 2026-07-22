from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.errors import ConfigurationError
from omnicorectl.services.control_station import (
    ControlStationService,
    RemoteControlStation,
)


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
            self.assertEqual(request.url.path, "/rw/controlstation/writeaccess/status")
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

    def test_scoped_write_access_registers_verifies_and_always_releases(self) -> None:
        station_id = "12345678-1234-5678-9abc-123456789abc"
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append(request.url.path)
            if request.url.path.endswith("/register/remote"):
                self.assertEqual(
                    request.headers["content-type"],
                    "application/x-www-form-urlencoded;v=2.0",
                )
                form = parse_qs(request.content.decode())
                self.assertEqual(form["control-station-id"], [f"{{{station_id}}}"])
                self.assertEqual(form["pincode"], ["483921"])
            if request.url.path.endswith("/status"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "control-station-write-access-held": "true",
                                "control-station-external-control-enabled": "true",
                                "held-by-control-station-Id": f"{{{station_id}}}",
                                "held-by-control-station-name": "omnicorectl tests",
                            }
                        ]
                    },
                )
            return httpx.Response(204)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            service = ControlStationService(client)
            station = RemoteControlStation("omnicorectl tests", station_id, "483921")
            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                with service.write_access(station) as status:
                    self.assertTrue(status.held)
                    raise RuntimeError("operation failed")

        self.assertEqual(
            calls,
            [
                "/rw/controlstation/register/remote",
                "/rw/controlstation/writeaccess/request",
                "/rw/controlstation/writeaccess/status",
                "/rw/controlstation/writeaccess/release",
            ],
        )

    def test_rejects_invalid_station_identity_before_network_access(self) -> None:
        with self.assertRaises(ConfigurationError):
            RemoteControlStation("test", "not-a-uuid", "1234")
        with self.assertRaises(ConfigurationError):
            RemoteControlStation(
                "test", "12345678-1234-5678-9abc-123456789abc", "not-digits"
            )

    def test_restart_scope_tolerates_release_failure(self) -> None:
        station_id = "12345678-1234-5678-9abc-123456789abc"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.url.path.endswith("/status"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "control-station-write-access-held": "true",
                                "control-station-external-control-enabled": "true",
                                "held-by-control-station-Id": f"{{{station_id}}}",
                                "held-by-control-station-name": "restart test",
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/release"):
                return httpx.Response(
                    503,
                    json={"status": {"code": -1, "msg": "restarting"}},
                )
            return httpx.Response(204)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            station = RemoteControlStation("restart test", station_id, "1234")
            with ControlStationService(client).write_access(
                station, best_effort_release=True
            ):
                pass


if __name__ == "__main__":
    unittest.main()
