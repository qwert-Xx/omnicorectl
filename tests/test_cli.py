from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from omnicorectl.cli import (
    _format_modules,
    _format_networks,
    _format_status,
    _format_tasks,
    _write_source,
    build_parser,
    main,
)
from omnicorectl.services.controller import ControllerStatus
from omnicorectl.services.io import IoNetwork
from omnicorectl.services.rapid import ModuleSource, RapidModule, RapidTask


STATUS = ControllerStatus(
    name="460-300278",
    controller_id="460-300278",
    controller_type="v250xt",
    mac_address="e0:02:a5:0b:60:f6",
    operation_mode="MANR",
    controller_state="motoroff",
    rapid_execution="stopped",
    execution_cycle="forever",
)


class CliTests(unittest.TestCase):
    def test_status_json_has_stable_machine_keys(self) -> None:
        output = json.loads(_format_status(STATUS, as_json=True))
        self.assertEqual(output["controller_id"], "460-300278")
        self.assertEqual(output["rapid_execution"], "stopped")

    def test_status_text_is_human_readable(self) -> None:
        output = _format_status(STATUS, as_json=False)
        self.assertIn("Operation mode:    MANR", output)
        self.assertIn("Controller state:  motoroff", output)

    def test_missing_connection_configuration_returns_exit_2(self) -> None:
        stderr = io.StringIO()
        clean_environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OMNICORE_")
        }
        with patch.dict(os.environ, clean_environment, clear=True):
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["controller", "status"])
        self.assertEqual(exit_code, 2)
        self.assertIn("missing --host", stderr.getvalue())

    def test_non_positive_timeout_is_rejected_by_parser(self) -> None:
        parser = build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                parser.parse_args(
                    ["--timeout", "0", "controller", "status"]
                )
        self.assertEqual(raised.exception.code, 2)

    def test_rapid_tasks_table_and_json(self) -> None:
        task = RapidTask("T_ROB1", "normal", "loaded", "ready", True, True)
        table = _format_tasks([task], as_json=False)
        self.assertIn("NAME", table)
        self.assertIn("T_ROB1", table)
        self.assertIn("yes", table)
        data = json.loads(_format_tasks([task], as_json=True))
        self.assertEqual(data[0]["name"], "T_ROB1")
        self.assertTrue(data[0]["motion_task"])

    def test_rapid_modules_table_and_json(self) -> None:
        modules = [
            RapidModule("T_ROB1", "BASE", "SysMod"),
            RapidModule("T_ROB1", "EGM_StreamMotion", "ProgMod"),
        ]
        table = _format_modules(modules, as_json=False)
        self.assertIn("EGM_StreamMotion  ProgMod", table)
        data = json.loads(_format_modules(modules, as_json=True))
        self.assertEqual(data[0]["task"], "T_ROB1")
        self.assertEqual(data[1]["module_type"], "ProgMod")

    def test_rapid_source_is_written_verbatim(self) -> None:
        module = ModuleSource("T_ROB1", "Test", 7, 20, "MODULE Test\nENDMODULE\n")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            _write_source(module, as_json=False)
        self.assertEqual(stdout.getvalue(), module.source)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            _write_source(module, as_json=True)
        self.assertEqual(json.loads(stdout.getvalue())["change_count"], 7)

    def test_io_networks_table_and_json(self) -> None:
        networks = [IoNetwork("EtherCAT", "running", "started")]
        table = _format_networks(networks, as_json=False)
        self.assertIn("PHYSICAL STATE", table)
        self.assertIn("EtherCAT", table)
        data = json.loads(_format_networks(networks, as_json=True))
        self.assertEqual(data[0]["logical_state"], "started")


if __name__ == "__main__":
    unittest.main()
