from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from omnicorectl.cli import build_parser, main
from omnicorectl.output import (
    format_cfg_domains,
    format_cfg_instance,
    format_cfg_instances,
    format_cfg_types,
    format_devices,
    format_download_result,
    format_file_entries,
    format_modules,
    format_networks,
    format_signal_details,
    format_signals,
    format_status,
    format_tasks,
    write_source,
)
from omnicorectl.services.controller import ControllerStatus
from omnicorectl.services.files import DownloadResult, FileEntry
from omnicorectl.services.cfg import CfgDomain, CfgInstance, CfgType
from omnicorectl.services.io import IoDevice, IoNetwork, IoSignal, IoSignalDetails
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
        output = json.loads(format_status(STATUS, as_json=True))
        self.assertEqual(output["controller_id"], "460-300278")
        self.assertEqual(output["rapid_execution"], "stopped")

    def test_status_text_is_human_readable(self) -> None:
        output = format_status(STATUS, as_json=False)
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
        table = format_tasks([task], as_json=False)
        self.assertIn("NAME", table)
        self.assertIn("T_ROB1", table)
        self.assertIn("yes", table)
        data = json.loads(format_tasks([task], as_json=True))
        self.assertEqual(data[0]["name"], "T_ROB1")
        self.assertTrue(data[0]["motion_task"])

    def test_rapid_modules_table_and_json(self) -> None:
        modules = [
            RapidModule("T_ROB1", "BASE", "SysMod"),
            RapidModule("T_ROB1", "EGM_StreamMotion", "ProgMod"),
        ]
        table = format_modules(modules, as_json=False)
        self.assertIn("EGM_StreamMotion  ProgMod", table)
        data = json.loads(format_modules(modules, as_json=True))
        self.assertEqual(data[0]["task"], "T_ROB1")
        self.assertEqual(data[1]["module_type"], "ProgMod")

    def test_rapid_source_is_written_verbatim(self) -> None:
        module = ModuleSource("T_ROB1", "Test", 7, 20, "MODULE Test\nENDMODULE\n")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            write_source(module, as_json=False)
        self.assertEqual(stdout.getvalue(), module.source)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            write_source(module, as_json=True)
        self.assertEqual(json.loads(stdout.getvalue())["change_count"], 7)

    def test_io_networks_table_and_json(self) -> None:
        networks = [IoNetwork("EtherCAT", "running", "started")]
        table = format_networks(networks, as_json=False)
        self.assertIn("PHYSICAL STATE", table)
        self.assertIn("EtherCAT", table)
        data = json.loads(format_networks(networks, as_json=True))
        self.assertEqual(data[0]["logical_state"], "started")

    def test_io_devices_table_and_json(self) -> None:
        devices = [IoDevice("EtherCAT", "EC_Internal_Device", "running", "enabled", "")]
        table = format_devices(devices, as_json=False)
        self.assertIn("EC_Internal_Device", table)
        self.assertIn("ADDRESS", table)
        data = json.loads(format_devices(devices, as_json=True))
        self.assertEqual(data[0]["network"], "EtherCAT")
        self.assertEqual(data[0]["address"], "")

    def test_io_signals_table_and_json(self) -> None:
        signals = [
            IoSignal(
                "EtherCAT",
                "EC_Internal_Device",
                "EtherCAT_DI",
                "DI",
                "default",
                "1",
                "not simulated",
            )
        ]
        table = format_signals(signals, as_json=False)
        self.assertIn("EtherCAT_DI", table)
        self.assertIn("EC_Internal_Device", table)
        data = json.loads(format_signals(signals, as_json=True))
        self.assertEqual(data[0]["signal_type"], "DI")
        self.assertEqual(data[0]["value"], "1")

    def test_io_signal_details_text_and_json(self) -> None:
        signal = IoSignalDetails(
            "Network",
            "Device",
            "Signal",
            "DI",
            "internal",
            "1",
            "not simulated",
            "1",
            "valid",
            "good",
            "Internal/Read-only",
            "None",
            "N/A",
        )
        text = format_signal_details(signal, as_json=False)
        self.assertIn("Network/Device/Signal", text)
        self.assertIn("Quality:         good", text)
        data = json.loads(format_signal_details(signal, as_json=True))
        self.assertEqual(data["physical_value"], "1")

    def test_cfg_domains_text_and_json(self) -> None:
        domains = [CfgDomain("EIO"), CfgDomain("MOC")]
        self.assertEqual(format_cfg_domains(domains, as_json=False), "EIO\nMOC")
        data = json.loads(format_cfg_domains(domains, as_json=True))
        self.assertEqual(data, [{"name": "EIO"}, {"name": "MOC"}])

    def test_cfg_types_text_and_json(self) -> None:
        cfg_types = [CfgType("EIO", "EIO_SIGNAL"), CfgType("EIO", "ETHERCAT_NETWORK")]
        text = format_cfg_types(cfg_types, as_json=False)
        self.assertEqual(text, "EIO_SIGNAL\nETHERCAT_NETWORK")
        data = json.loads(format_cfg_types(cfg_types, as_json=True))
        self.assertEqual(data[0], {"domain": "EIO", "name": "EIO_SIGNAL"})

    def test_cfg_instances_table_and_json(self) -> None:
        instances = [
            CfgInstance("EIO", "EIO_SIGNAL", "Signal1", "10", False, {"Name": "Signal1"})
        ]
        table = format_cfg_instances(instances, as_json=False)
        self.assertIn("INSTANCE ID", table)
        self.assertIn("Signal1", table)
        data = json.loads(format_cfg_instances(instances, as_json=True))
        self.assertEqual(data[0]["attributes"]["Name"], "Signal1")

    def test_cfg_instance_details_text_and_json(self) -> None:
        instance = CfgInstance(
            "EIO",
            "ETHERCAT_INTERNAL_DEVICE",
            "EC_Internal_Device",
            "42",
            False,
            {"OutputSize": "64", "Label": ""},
        )
        text = format_cfg_instance(instance, as_json=False)
        self.assertIn("EIO/ETHERCAT_INTERNAL_DEVICE/EC_Internal_Device", text)
        self.assertIn("OutputSize  64", text)
        data = json.loads(format_cfg_instance(instance, as_json=True))
        self.assertEqual(data["instance_id"], "42")

    def test_file_entries_table_and_json(self) -> None:
        entries = [
            FileEntry(
                "/$HOME/Dashboard.xml",
                "Dashboard.xml",
                False,
                6349,
                False,
                "created",
                "modified",
            ),
            FileEntry("/$HOME/Code", "Code", True, None, False, "created", "modified"),
        ]
        table = format_file_entries(entries, as_json=False)
        self.assertIn("Dashboard.xml", table)
        self.assertIn("dir", table)
        data = json.loads(format_file_entries(entries, as_json=True))
        self.assertEqual(data[0]["size"], 6349)
        self.assertTrue(data[1]["is_directory"])

    def test_download_result_text_and_json(self) -> None:
        result = DownloadResult("/$HOME/test.bin", "/tmp/test.bin", 123)
        text = format_download_result(result, as_json=False)
        self.assertIn("123 bytes", text)
        data = json.loads(format_download_result(result, as_json=True))
        self.assertEqual(data["remote_path"], "/$HOME/test.bin")


if __name__ == "__main__":
    unittest.main()
