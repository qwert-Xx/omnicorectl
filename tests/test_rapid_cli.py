from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from unittest.mock import patch

from omnicorectl.cli import build_parser, main
from omnicorectl.errors import ConfigurationError
from omnicorectl.rapid_cli import dispatch_rapid
from omnicorectl.rws import RwsClient
from omnicorectl.services.control_station import RemoteControlStation


class RapidCliTests(unittest.TestCase):
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
