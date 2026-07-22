"""Command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import asdict
from typing import Sequence

from omnicorectl.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    NetworkError,
    OmnicoreError,
    ProtocolError,
)
from omnicorectl.rws import RwsClient
from omnicorectl.services.cfg import CfgDomain, CfgInstance, CfgService, CfgType
from omnicorectl.services.controller import ControllerService, ControllerStatus
from omnicorectl.services.io import (
    IoDevice,
    IoNetwork,
    IoService,
    IoSignal,
    IoSignalDetails,
)
from omnicorectl.services.rapid import ModuleSource, RapidModule, RapidService, RapidTask


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omnicorectl",
        description="Manage ABB OmniCore controllers through RWS 2.0.",
    )
    parser.add_argument("--host", default=os.getenv("OMNICORE_HOST"))
    parser.add_argument("--username", default=os.getenv("OMNICORE_USERNAME"))
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=_env_flag("OMNICORE_INSECURE"),
        help="disable TLS certificate verification (required for factory certificates)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=os.getenv("OMNICORE_TIMEOUT", "10"),
        metavar="SECONDS",
    )

    groups = parser.add_subparsers(dest="group", required=True)
    controller = groups.add_parser("controller", help="controller information")
    controller_commands = controller.add_subparsers(dest="command", required=True)
    status = controller_commands.add_parser("status", help="show current controller status")
    status.add_argument("--json", action="store_true", dest="as_json")

    rapid = groups.add_parser("rapid", help="RAPID program information")
    rapid_commands = rapid.add_subparsers(dest="command", required=True)
    tasks = rapid_commands.add_parser("tasks", help="list RAPID tasks")
    tasks.add_argument("--json", action="store_true", dest="as_json")
    modules = rapid_commands.add_parser("modules", help="list modules in a RAPID task")
    modules.add_argument("task", help="RAPID task name, for example T_ROB1")
    modules.add_argument("--json", action="store_true", dest="as_json")
    read = rapid_commands.add_parser("read", help="write RAPID module source to stdout")
    read.add_argument("task", help="RAPID task name, for example T_ROB1")
    read.add_argument("module", help="RAPID module name")
    read.add_argument("--json", action="store_true", dest="as_json")

    io_group = groups.add_parser("io", help="I/O system information")
    io_commands = io_group.add_subparsers(dest="command", required=True)
    networks = io_commands.add_parser("networks", help="list I/O networks")
    networks.add_argument("--json", action="store_true", dest="as_json")
    devices = io_commands.add_parser("devices", help="list devices on an I/O network")
    devices.add_argument("network", help="I/O network name, for example EtherCAT")
    devices.add_argument("--json", action="store_true", dest="as_json")
    signals = io_commands.add_parser("signals", help="list or search I/O signals")
    signals.add_argument("--network")
    signals.add_argument("--device")
    signals.add_argument("--type", dest="signal_type", choices=("DI", "DO", "AI", "AO", "GI", "GO"))
    signals.add_argument("--name")
    signals.add_argument("--json", action="store_true", dest="as_json")
    io_get = io_commands.add_parser("get", help="read one I/O signal")
    io_get.add_argument("network")
    io_get.add_argument("device")
    io_get.add_argument("name")
    io_get.add_argument("--json", action="store_true", dest="as_json")

    cfg = groups.add_parser("cfg", help="controller configuration database")
    cfg_commands = cfg.add_subparsers(dest="command", required=True)
    domains = cfg_commands.add_parser("domains", help="list CFG domains")
    domains.add_argument("--json", action="store_true", dest="as_json")
    cfg_types = cfg_commands.add_parser("types", help="list types in a CFG domain")
    cfg_types.add_argument("domain", help="CFG domain, for example EIO")
    cfg_types.add_argument("--json", action="store_true", dest="as_json")
    instances = cfg_commands.add_parser("instances", help="list CFG type instances")
    instances.add_argument("domain")
    instances.add_argument("cfg_type")
    instances.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        host = _required(args.host, "--host or OMNICORE_HOST")
        username = _required(args.username, "--username or OMNICORE_USERNAME")
        password = _password()

        with RwsClient(
            host,
            username,
            password,
            verify_tls=not args.insecure,
            timeout=args.timeout,
        ) as client:
            if (args.group, args.command) == ("controller", "status"):
                status = ControllerService(client).status()
                print(_format_status(status, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("rapid", "tasks"):
                tasks = RapidService(client).list_tasks()
                print(_format_tasks(tasks, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("rapid", "modules"):
                modules = RapidService(client).list_modules(args.task)
                print(_format_modules(modules, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("rapid", "read"):
                source = RapidService(client).get_module_source(args.task, args.module)
                _write_source(source, as_json=args.as_json)
                return 0
            if (args.group, args.command) == ("io", "networks"):
                networks = IoService(client).list_networks()
                print(_format_networks(networks, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("io", "devices"):
                devices = IoService(client).list_devices(args.network)
                print(_format_devices(devices, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("io", "signals"):
                signals = IoService(client).list_signals(
                    network=args.network,
                    device=args.device,
                    signal_type=args.signal_type,
                    name=args.name,
                )
                print(_format_signals(signals, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("io", "get"):
                signal = IoService(client).get_signal(
                    args.network, args.device, args.name
                )
                print(_format_signal_details(signal, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("cfg", "domains"):
                domains = CfgService(client).list_domains()
                print(_format_cfg_domains(domains, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("cfg", "types"):
                cfg_types = CfgService(client).list_types(args.domain)
                print(_format_cfg_types(cfg_types, as_json=args.as_json))
                return 0
            if (args.group, args.command) == ("cfg", "instances"):
                instances = CfgService(client).list_instances(
                    args.domain, args.cfg_type
                )
                print(_format_cfg_instances(instances, as_json=args.as_json))
                return 0
        raise ConfigurationError("unsupported command")
    except ConfigurationError as exc:
        return _error(exc, 2)
    except NetworkError as exc:
        return _error(exc, 3)
    except AuthenticationError as exc:
        return _error(exc, 4)
    except AuthorizationError as exc:
        return _error(exc, 5)
    except (ProtocolError, OmnicoreError) as exc:
        return _error(exc, 6)


def _format_status(status: ControllerStatus, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(asdict(status), indent=2, ensure_ascii=False)
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


def _format_tasks(tasks: list[RapidTask], *, as_json: bool) -> str:
    if as_json:
        return json.dumps([asdict(task) for task in tasks], indent=2, ensure_ascii=False)
    if not tasks:
        return "No RAPID tasks found."

    headings = ("NAME", "TYPE", "TASK STATE", "EXEC STATE", "ACTIVE", "MOTION")
    rows = [
        (
            task.name,
            task.task_type,
            task.task_state,
            task.execution_state,
            "yes" if task.active else "no",
            "yes" if task.motion_task else "no",
        )
        for task in tasks
    ]
    widths = [
        max(len(headings[index]), *(len(row[index]) for row in rows))
        for index in range(len(headings))
    ]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    return "\n".join((format_row(headings), format_row(tuple("-" * n for n in widths)), *(format_row(row) for row in rows)))


def _format_modules(modules: list[RapidModule], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(module) for module in modules], indent=2, ensure_ascii=False
        )
    if not modules:
        return "No RAPID modules found."
    name_width = max(len("NAME"), *(len(module.name) for module in modules))
    lines = [f"{'NAME'.ljust(name_width)}  TYPE", f"{'-' * name_width}  ------"]
    lines.extend(
        f"{module.name.ljust(name_width)}  {module.module_type}"
        for module in modules
    )
    return "\n".join(lines)


def _write_source(module: ModuleSource, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(module), indent=2, ensure_ascii=False))
        return
    sys.stdout.write(module.source)
    if not module.source.endswith("\n"):
        sys.stdout.write("\n")


def _format_networks(networks: list[IoNetwork], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(network) for network in networks], indent=2, ensure_ascii=False
        )
    if not networks:
        return "No I/O networks found."
    headings = ("NAME", "PHYSICAL STATE", "LOGICAL STATE")
    rows = [
        (network.name, network.physical_state, network.logical_state)
        for network in networks
    ]
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


def _format_devices(devices: list[IoDevice], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(device) for device in devices], indent=2, ensure_ascii=False
        )
    if not devices:
        return "No I/O devices found."
    headings = ("NAME", "PHYSICAL STATE", "LOGICAL STATE", "ADDRESS")
    rows = [
        (
            device.name,
            device.physical_state,
            device.logical_state,
            device.address or "-",
        )
        for device in devices
    ]
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


def _format_signals(signals: list[IoSignal], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(signal) for signal in signals], indent=2, ensure_ascii=False
        )
    if not signals:
        return "No I/O signals found."
    headings = ("NETWORK", "DEVICE", "NAME", "TYPE", "VALUE", "STATE")
    rows = [
        (
            signal.network or "-",
            signal.device or "-",
            signal.name,
            signal.signal_type,
            signal.value,
            signal.state,
        )
        for signal in signals
    ]
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


def _format_signal_details(signal: IoSignalDetails, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(asdict(signal), indent=2, ensure_ascii=False)
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


def _format_cfg_domains(domains: list[CfgDomain], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(domain) for domain in domains], indent=2, ensure_ascii=False
        )
    if not domains:
        return "No CFG domains found."
    return "\n".join(domain.name for domain in domains)


def _format_cfg_types(cfg_types: list[CfgType], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(cfg_type) for cfg_type in cfg_types], indent=2, ensure_ascii=False
        )
    if not cfg_types:
        return "No CFG types found."
    return "\n".join(cfg_type.name for cfg_type in cfg_types)


def _format_cfg_instances(instances: list[CfgInstance], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [asdict(instance) for instance in instances], indent=2, ensure_ascii=False
        )
    if not instances:
        return "No CFG instances found."
    headings = ("NAME", "INSTANCE ID", "READ ONLY")
    rows = [
        (instance.name, instance.instance_id, "yes" if instance.read_only else "no")
        for instance in instances
    ]
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


def _password() -> str:
    password = os.getenv("OMNICORE_PASSWORD")
    if password is not None:
        return _required(password, "OMNICORE_PASSWORD")
    if not sys.stdin.isatty():
        raise ConfigurationError(
            "OMNICORE_PASSWORD is required when standard input is not interactive"
        )
    password = getpass.getpass("Controller password: ")
    return _required(password, "controller password")


def _required(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(f"missing {label}")
    return value.strip()


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _error(exc: Exception, exit_code: int) -> int:
    print(f"omnicorectl: {exc}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
