from __future__ import annotations

import json
import unittest

import httpx

from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.rws import RwsClient
from omnicorectl.services.controller import ControllerService


RESPONSES = {
    "/ctrl/identity": {
        "state": [
            {
                "_type": "ctrl-identity-info",
                "ctrl-name": "460-300278",
                "ctrl-id": "460-300278",
                "ctrl-type": "v250xt",
                "ctrl-mac": "e0:02:a5:0b:60:f6",
                "future-field": "must be ignored",
            }
        ]
    },
    "/rw/panel/opmode": {"state": [{"opmode": "MANR"}]},
    "/rw/panel/ctrl-state": {"state": [{"ctrlstate": "motoroff"}]},
    "/rw/rapid/execution": {
        "state": [{"ctrlexecstate": "stopped", "cycle": "forever"}]
    },
}


class ControllerStatusTests(unittest.TestCase):
    def test_reads_and_combines_controller_resources(self) -> None:
        requested_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            self.assertEqual(request.headers["accept"], "application/hal+json;v=2.0")
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(200, json=RESPONSES[request.url.path])

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            status = ControllerService(client).status()

        self.assertEqual(status.name, "460-300278")
        self.assertEqual(status.controller_type, "v250xt")
        self.assertEqual(status.operation_mode, "MANR")
        self.assertEqual(status.controller_state, "motoroff")
        self.assertEqual(status.rapid_execution, "stopped")
        self.assertEqual(
            requested_paths,
            [
                "/ctrl/identity",
                "/rw/panel/opmode",
                "/rw/panel/ctrl-state",
                "/rw/rapid/execution",
                "/logout",
            ],
        )

    def test_mock_fixtures_are_json_serializable(self) -> None:
        json.dumps(RESPONSES)

    def test_requests_only_normal_warm_restart_with_implicit_mastership(self) -> None:
        calls: list[tuple[str, str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append((request.method, str(request.url), request.content.decode()))
            if request.method == "GET":
                return httpx.Response(200, json={"state": [{"restart-count": "7"}]})
            return httpx.Response(204)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            result = ControllerService(client).warm_restart()

        self.assertTrue(result.accepted)
        self.assertEqual(result.mode, "restart")
        self.assertEqual(result.restart_count_before, 7)
        self.assertEqual(
            calls,
            [
                (
                    "GET",
                    "https://192.0.2.1/ctrl/restart/restartcount",
                    "",
                ),
                (
                    "POST",
                    "https://192.0.2.1/ctrl/restart?mastership=implicit",
                    "restart-mode=restart",
                ),
            ],
        )

    def test_switches_motor_state_and_verifies_readback(self) -> None:
        state = "motoron"
        calls: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal state
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append((request.method, request.content.decode()))
            if request.method == "POST":
                self.assertEqual(request.url.path, "/rw/panel/ctrl-state")
                self.assertEqual(request.content.decode(), "ctrl-state=motoroff")
                state = "motoroff"
                return httpx.Response(204)
            return httpx.Response(200, json={"state": [{"ctrlstate": state}]})

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            result = ControllerService(client).set_motor_state("motoroff")

        self.assertTrue(result.changed)
        self.assertEqual(result.state_before, "motoron")
        self.assertEqual(result.state_after, "motoroff")
        self.assertEqual(
            calls,
            [
                ("GET", ""),
                ("POST", "ctrl-state=motoroff"),
                ("GET", ""),
            ],
        )

    def test_motor_state_noop_and_invalid_safety_transition(self) -> None:
        guardstop_requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            guardstop_requests.append(request.method)
            return httpx.Response(200, json={"state": [{"ctrlstate": "guardstop"}]})

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            service = ControllerService(client)
            with self.assertRaisesRegex(ConfigurationError, "guardstop"):
                service.set_motor_state("motoron")
        self.assertEqual(guardstop_requests, ["GET"])

        noop_requests: list[str] = []

        def motoron_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            noop_requests.append(request.method)
            return httpx.Response(200, json={"state": [{"ctrlstate": "motoron"}]})

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(motoron_handler),
            request_interval=0,
        ) as client:
            result = ControllerService(client).set_motor_state("motoron")
        self.assertFalse(result.changed)
        self.assertEqual(noop_requests, ["GET"])

    def test_motor_on_stops_polling_when_safety_state_appears(self) -> None:
        states = iter(("motoroff", "guardstop"))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.method == "POST":
                return httpx.Response(204)
            return httpx.Response(200, json={"state": [{"ctrlstate": next(states)}]})

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ProtocolError, "guardstop"):
                ControllerService(client).set_motor_state("motoron")


if __name__ == "__main__":
    unittest.main()
