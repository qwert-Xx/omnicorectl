"""Human-readable and JSON output rendering, independent of command dispatch."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from omnicorectl.services.backup import BackupResult, BackupStatus
from omnicorectl.services.cfg import CfgChange, CfgDomain, CfgInstance, CfgType
from omnicorectl.services.controller import ControllerStatus, RestartResult
from omnicorectl.services.control_station import WriteAccessStatus
from omnicorectl.services.files import (
    DeleteResult,
    DownloadResult,
    FileEntry,
    UploadResult,
)
from omnicorectl.services.io import IoDevice, IoNetwork, IoSignal, IoSignalDetails
from omnicorectl.services.rapid import ModuleSource, RapidModule, RapidTask


def format_status(status: ControllerStatus, *, as_json: bool) -> str:
    if as_json:
        return _json_object(status)
    return "\n".join(
        (
            f"Name:              {status.name}",
            f"Controller ID:     {status.controller_id}",
            f"Controller type:   {status.controller_type}",
            f"MAC address:       {status.mac_address}",
            f"Operation mode:    {status.operation_mode}",
            f"Controller state:  {status.controller_state}",
            f"RAPID execution:   {status.rapid_execution}",
            f"Execution cycle:   {status.execution_cycle}",
        )
    )


def format_restart_result(result: RestartResult, *, as_json: bool) -> str:
    if as_json:
        return _json_object(result)
    return (
        "Warm restart accepted; the controller connection may drop "
        f"(previous restart count: {result.restart_count_before})."
    )


def format_tasks(tasks: list[RapidTask], *, as_json: bool) -> str:
    if as_json:
        return _json_list(tasks)
    if not tasks:
        return "No RAPID tasks found."
    return _format_table(
        ("NAME", "TYPE", "TASK STATE", "EXEC STATE", "ACTIVE", "MOTION"),
        [
            (
                task.name,
                task.task_type,
                task.task_state,
                task.execution_state,
                _yes_no(task.active),
                _yes_no(task.motion_task),
            )
            for task in tasks
        ],
    )


def format_modules(modules: list[RapidModule], *, as_json: bool) -> str:
    if as_json:
        return _json_list(modules)
    if not modules:
        return "No RAPID modules found."
    return _format_table(
        ("NAME", "TYPE"),
        [(module.name, module.module_type) for module in modules],
    )


def write_source(module: ModuleSource, *, as_json: bool) -> None:
    if as_json:
        print(_json_object(module))
        return
    sys.stdout.write(module.source)
    if not module.source.endswith("\n"):
        sys.stdout.write("\n")


def format_networks(networks: list[IoNetwork], *, as_json: bool) -> str:
    if as_json:
        return _json_list(networks)
    if not networks:
        return "No I/O networks found."
    return _format_table(
        ("NAME", "PHYSICAL STATE", "LOGICAL STATE"),
        [
            (network.name, network.physical_state, network.logical_state)
            for network in networks
        ],
    )


def format_devices(devices: list[IoDevice], *, as_json: bool) -> str:
    if as_json:
        return _json_list(devices)
    if not devices:
        return "No I/O devices found."
    return _format_table(
        ("NAME", "PHYSICAL STATE", "LOGICAL STATE", "ADDRESS"),
        [
            (
                device.name,
                device.physical_state,
                device.logical_state,
                device.address or "-",
            )
            for device in devices
        ],
    )


def format_signals(signals: list[IoSignal], *, as_json: bool) -> str:
    if as_json:
        return _json_list(signals)
    if not signals:
        return "No I/O signals found."
    return _format_table(
        ("NETWORK", "DEVICE", "NAME", "TYPE", "VALUE", "STATE"),
        [
            (
                signal.network or "-",
                signal.device or "-",
                signal.name,
                signal.signal_type,
                signal.value,
                signal.state,
            )
            for signal in signals
        ],
    )


def format_signal_details(signal: IoSignalDetails, *, as_json: bool) -> str:
    if as_json:
        return _json_object(signal)
    return "\n".join(
        (
            f"Signal:          {signal.network}/{signal.device}/{signal.name}",
            f"Type:            {signal.signal_type}",
            f"Category:        {signal.category}",
            f"Logical value:   {signal.logical_value}",
            f"Logical state:   {signal.logical_state}",
            f"Physical value:  {signal.physical_value}",
            f"Physical state:  {signal.physical_state}",
            f"Quality:         {signal.quality}",
            f"Access level:    {signal.access_level}",
            f"Write access:    {signal.write_access}",
            f"Safety level:    {signal.safety_level}",
        )
    )


def format_cfg_domains(domains: list[CfgDomain], *, as_json: bool) -> str:
    if as_json:
        return _json_list(domains)
    if not domains:
        return "No CFG domains found."
    return "\n".join(domain.name for domain in domains)


def format_cfg_types(cfg_types: list[CfgType], *, as_json: bool) -> str:
    if as_json:
        return _json_list(cfg_types)
    if not cfg_types:
        return "No CFG types found."
    return "\n".join(cfg_type.name for cfg_type in cfg_types)


def format_cfg_instances(instances: list[CfgInstance], *, as_json: bool) -> str:
    if as_json:
        return _json_list(instances)
    if not instances:
        return "No CFG instances found."
    return _format_table(
        ("NAME", "INSTANCE ID", "READ ONLY"),
        [
            (instance.name, instance.instance_id, _yes_no(instance.read_only))
            for instance in instances
        ],
    )


def format_cfg_instance(instance: CfgInstance, *, as_json: bool) -> str:
    if as_json:
        return _json_object(instance)
    lines = [
        f"Instance:     {instance.domain}/{instance.cfg_type}/{instance.name}",
        f"Instance ID:  {instance.instance_id}",
        f"Read only:    {_yes_no(instance.read_only)}",
        "Attributes:",
    ]
    if not instance.attributes:
        lines.append("  (none)")
    else:
        width = max(len(key) for key in instance.attributes)
        lines.extend(
            f"  {key.ljust(width)}  {value}"
            for key, value in instance.attributes.items()
        )
    return "\n".join(lines)


def format_cfg_change(change: CfgChange, *, as_json: bool) -> str:
    if as_json:
        return _json_object(change)
    if not change.changed:
        return (
            f"CFG unchanged: {change.domain}/{change.cfg_type}/{change.instance} "
            f"{change.attribute}={change.old_value!r}"
        )
    return "\n".join(
        (
            f"CFG updated: {change.domain}/{change.cfg_type}/{change.instance}",
            f"Attribute:   {change.attribute}",
            f"Old value:   {change.old_value}",
            f"New value:   {change.new_value}",
            "Validated:   yes",
            "Restart required: yes",
        )
    )


def format_file_entries(entries: list[FileEntry], *, as_json: bool) -> str:
    if as_json:
        return _json_list(entries)
    if not entries:
        return "Directory is empty."
    return _format_table(
        ("TYPE", "SIZE", "READ ONLY", "MODIFIED", "NAME"),
        [
            (
                "dir" if entry.is_directory else "file",
                "-" if entry.size is None else str(entry.size),
                _yes_no(entry.read_only),
                entry.modified,
                entry.name,
            )
            for entry in entries
        ],
    )


def format_download_result(result: DownloadResult, *, as_json: bool) -> str:
    if as_json:
        return _json_object(result)
    return f"Downloaded {result.remote_path} -> {result.local_path} ({result.bytes_written} bytes)"


def format_upload_result(result: UploadResult, *, as_json: bool) -> str:
    if as_json:
        return _json_object(result)
    return f"Uploaded {result.local_path} -> {result.remote_path} ({result.bytes_written} bytes)"


def format_delete_result(result: DeleteResult, *, as_json: bool) -> str:
    if as_json:
        return _json_object(result)
    return f"Deleted {result.remote_path}"


def format_backup_status(status: BackupStatus, *, as_json: bool) -> str:
    if as_json:
        return _json_object(status)
    return f"Backup state: {status.state}"


def format_backup_result(result: BackupResult, *, as_json: bool) -> str:
    if as_json:
        return _json_object(result)
    kind = "archive" if result.archive else "directory"
    return (
        f"Backup ready ({kind}): {result.artifact_path} "
        f"[code {result.code}, progress {result.progress_uri}]"
    )


def format_write_access_status(status: WriteAccessStatus, *, as_json: bool) -> str:
    if as_json:
        return _json_object(status)
    return "\n".join(
        (
            f"Write access held:        {_yes_no(status.held)}",
            f"External control enabled: {_yes_no(status.external_control_enabled)}",
            f"Holder ID:                {status.holder_id}",
            f"Holder name:              {status.holder_name}",
        )
    )


def _format_table(headings: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [
        max(len(headings[index]), *(len(row[index]) for row in rows))
        for index in range(len(headings))
    ]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    separator = tuple("-" * width for width in widths)
    return "\n".join(
        (format_row(headings), format_row(separator), *(format_row(row) for row in rows))
    )


def _json_object(value: object) -> str:
    return json.dumps(asdict(value), indent=2, ensure_ascii=False)  # type: ignore[arg-type]


def _json_list(values: list[object]) -> str:
    return json.dumps(
        [asdict(value) for value in values],  # type: ignore[arg-type]
        indent=2,
        ensure_ascii=False,
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
