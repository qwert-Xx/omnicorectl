from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs

import httpx

from unittest.mock import patch

from omnicorectl.cli import build_parser, main
from omnicorectl.errors import ConfigurationError, RwsHttpError
from omnicorectl.rapid_cli import dispatch_rapid
from omnicorectl.rws import RwsClient
from omnicorectl.services.control_station import RemoteControlStation


class RapidCliTests(unittest.TestCase):
    def test_start_scopes_motion_control_inside_write_access(self) -> None:
        station_id = "12345678-1234-5678-9abc-123456789abc"
        motion_enabled = False
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal motion_enabled
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append(f"{request.method} {request.url.path}")
            if request.url.path.endswith("/writeaccess/status"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "control-station-write-access-held": "true",
                                "control-station-external-control-enabled": "true",
                                "held-by-control-station-Id": f"{{{station_id}}}",
                                "held-by-control-station-name": "rapid start test",
                            }
                        ]
                    },
                )
            if request.url.path == "/rw/controlstation/allowmotioncontrol":
                if request.method == "POST":
                    form = parse_qs(request.content.decode())
                    motion_enabled = form["allow-motion-control"] == ["true"]
                    return httpx.Response(204)
                return httpx.Response(
                    200,
                    json={
                        "state": [{"is-enabled": "true" if motion_enabled else "false"}]
                    },
                )
            if request.url.path == "/rw/rapid/execution/start":
                self.assertTrue(motion_enabled)
                form = parse_qs(request.content.decode())
                self.assertEqual(form["cycle"], ["once"])
                self.assertEqual(form["alltaskbytsp"], ["true"])
            return httpx.Response(204)

        args = build_parser().parse_args(
            [
                "rapid",
                "start",
                "--mode",
                "continue",
                "--cycle",
                "once",
                "--all-tasks",
                "--yes",
            ]
        )
        station = RemoteControlStation("rapid start test", station_id, "1234")
        with _client(handler) as client:
            dispatch_rapid(client, args, lambda: station)

        self.assertFalse(motion_enabled)
        self.assertEqual(
            calls,
            [
                "POST /rw/controlstation/register/remote",
                "POST /rw/controlstation/writeaccess/request",
                "GET /rw/controlstation/writeaccess/status",
                "POST /rw/controlstation/allowmotioncontrol",
                "GET /rw/controlstation/allowmotioncontrol",
                "POST /rw/rapid/execution/start",
                "POST /rw/controlstation/allowmotioncontrol",
                "GET /rw/controlstation/allowmotioncontrol",
                "POST /rw/controlstation/writeaccess/release",
            ],
        )

    def test_start_failure_still_disables_motion_control_and_releases_access(
        self,
    ) -> None:
        station_id = "12345678-1234-5678-9abc-123456789abc"
        motion_enabled = False
        released = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal motion_enabled, released
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.url.path.endswith("/writeaccess/status"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "control-station-write-access-held": "true",
                                "control-station-external-control-enabled": "true",
                                "held-by-control-station-Id": f"{{{station_id}}}",
                                "held-by-control-station-name": "rapid failure test",
                            }
                        ]
                    },
                )
            if request.url.path == "/rw/controlstation/allowmotioncontrol":
                if request.method == "POST":
                    form = parse_qs(request.content.decode())
                    motion_enabled = form["allow-motion-control"] == ["true"]
                    return httpx.Response(204)
                return httpx.Response(
                    200,
                    json={
                        "state": [{"is-enabled": "true" if motion_enabled else "false"}]
                    },
                )
            if request.url.path == "/rw/rapid/execution/start":
                self.assertTrue(motion_enabled)
                return httpx.Response(
                    400,
                    json={"status": {"code": -1, "msg": "start rejected"}},
                )
            if request.url.path.endswith("/writeaccess/release"):
                released = True
            return httpx.Response(204)

        args = build_parser().parse_args(["rapid", "start", "--yes"])
        station = RemoteControlStation("rapid failure test", station_id, "1234")
        with _client(handler) as client:
            with self.assertRaises(RwsHttpError):
                dispatch_rapid(client, args, lambda: station)

        self.assertFalse(motion_enabled)
        self.assertTrue(released)

    def test_stop_and_reset_do_not_enable_motion_control(self) -> None:
        station_id = "12345678-1234-5678-9abc-123456789abc"

        for command, action_path in (
            ("stop", "/rw/rapid/execution/stop"),
            ("reset-pp", "/rw/rapid/execution/resetpp"),
        ):
            with self.subTest(command=command):
                calls: list[str] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    if request.url.path == "/logout":
                        return httpx.Response(200, json={})
                    calls.append(request.url.path)
                    self.assertNotEqual(
                        request.url.path, "/rw/controlstation/allowmotioncontrol"
                    )
                    if request.url.path.endswith("/writeaccess/status"):
                        return httpx.Response(
                            200,
                            json={
                                "state": [
                                    {
                                        "control-station-write-access-held": "true",
                                        "control-station-external-control-enabled": (
                                            "true"
                                        ),
                                        "held-by-control-station-Id": (
                                            f"{{{station_id}}}"
                                        ),
                                        "held-by-control-station-name": (
                                            "non-start test"
                                        ),
                                    }
                                ]
                            },
                        )
                    return httpx.Response(204)

                args = build_parser().parse_args(["rapid", command, "--yes"])
                station = RemoteControlStation("non-start test", station_id, "1234")
                with _client(handler) as client:
                    dispatch_rapid(client, args, lambda: station)

                self.assertIn(action_path, calls)

    def test_local_validation_needs_no_controller_configuration(self) -> None:
        clean_environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OMNICORE_")
        }
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Local.mod"
            source.write_text("MODULE Local\nENDMODULE\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.dict(os.environ, clean_environment, clear=True):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "rapid",
                            "validate",
                            str(source),
                            "--expected-module",
                            "Local",
                            "--json",
                        ]
                    )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["module_name"], "Local")

    def test_parser_exposes_edit_deploy_debug_and_symbol_commands(self) -> None:
        parser = build_parser()
        write = parser.parse_args(
            [
                "rapid",
                "write",
                "T_ROB1",
                "MainModule",
                "MainModule.mod",
                "--if-change-count",
                "12",
                "--yes",
            ]
        )
        self.assertEqual(write.command, "write")
        self.assertEqual(write.if_change_count, 12)
        self.assertFalse(write.no_rollback)

        pp = parser.parse_args(
            ["rapid", "pp", "cursor", "T_ROB1", "MainModule", "10", "3", "--yes"]
        )
        self.assertEqual(pp.operation, "cursor")
        self.assertEqual(pp.line, 10)

        symbol = parser.parse_args(
            ["rapid", "symbol", "search", "RAPID/T_ROB1", "--symbol-type", "per"]
        )
        self.assertEqual(symbol.symbol_type, "per")

    def test_write_dry_run_validates_and_diffs_without_requesting_write_access(
        self,
    ) -> None:
        original = "MODULE MainModule\nENDMODULE\n"
        changed = "MODULE MainModule\n    ! agent edit\nENDMODULE\n"
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            requests.append(f"{request.method} {request.url.path}")
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "change-count": "7",
                            "module-length": str(len(original)),
                            "module-text": original,
                        }
                    ]
                },
            )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(changed, encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "rapid",
                    "write",
                    "T_ROB1",
                    "MainModule",
                    str(source),
                    "--dry-run",
                ]
            )
            stdout = io.StringIO()
            with _client(handler) as client, contextlib.redirect_stdout(stdout):
                exit_code = dispatch_rapid(client, args, _unexpected_station)

        self.assertEqual(exit_code, 0)
        self.assertIn("+    ! agent edit", stdout.getvalue())
        self.assertEqual(
            requests,
            ["GET /rw/rapid/tasks/T_ROB1/modules/MainModule/text"],
        )

    def test_write_dry_run_rejects_stale_change_count(self) -> None:
        original = "MODULE MainModule\nENDMODULE\n"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "change-count": "7",
                            "module-length": str(len(original)),
                            "module-text": original,
                        }
                    ]
                },
            )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "MainModule.mod"
            source.write_text(original, encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "rapid",
                    "write",
                    "T_ROB1",
                    "MainModule",
                    str(source),
                    "--if-change-count",
                    "6",
                    "--dry-run",
                ]
            )
            with _client(handler) as client:
                with self.assertRaisesRegex(ConfigurationError, "concurrently"):
                    dispatch_rapid(client, args, _unexpected_station)

    def test_search_not_found_emits_valid_json_null(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"state": [{"Row": "0", "Column": "0"}]})

        args = build_parser().parse_args(
            ["rapid", "search", "T_ROB1", "MainModule", "missing", "--json"]
        )
        stdout = io.StringIO()
        with _client(handler) as client, contextlib.redirect_stdout(stdout):
            dispatch_rapid(client, args, _unexpected_station)
        self.assertIsNone(json.loads(stdout.getvalue()))


def _unexpected_station() -> RemoteControlStation:
    raise AssertionError("dry-run/read command unexpectedly requested write access")


def _client(handler: object) -> RwsClient:
    return RwsClient(
        "192.0.2.1",
        "test-user",
        "test-password",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        request_interval=0,
    )


if __name__ == "__main__":
    unittest.main()
