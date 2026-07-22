"""Command-line parsing and dispatch."""

from __future__ import annotations

import argparse
import getpass
import os
import socket
import sys
from pathlib import Path
from typing import Sequence
from uuid import UUID, uuid5

from omnicorectl.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    NetworkError,
    OmnicoreError,
    ProtocolError,
)
from omnicorectl.output import (
    format_backup_result,
    format_backup_status,
    format_cfg_change,
    format_cfg_domains,
    format_cfg_instance,
    format_cfg_instances,
    format_cfg_types,
    format_delete_result,
    format_devices,
    format_download_result,
    format_file_entries,
    format_modules,
    format_networks,
    format_restart_result,
    format_signal_details,
    format_signals,
    format_status,
    format_tasks,
    format_upload_result,
    format_write_access_status,
    write_source,
)
from omnicorectl.rws import RwsClient
from omnicorectl.services.backup import BackupService
from omnicorectl.services.cfg import CfgService
from omnicorectl.services.controller import ControllerService
from omnicorectl.services.control_station import (
    ControlStationService,
    RemoteControlStation,
)
from omnicorectl.services.files import FileService
from omnicorectl.services.io import IoService
from omnicorectl.services.rapid import RapidService


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
    parser.add_argument(
        "--station-name",
        default=os.getenv("OMNICORE_STATION_NAME", f"omnicorectl@{socket.gethostname()}"),
        help="RW8 remote Control Station display name for write commands",
    )
    parser.add_argument(
        "--station-id",
        default=os.getenv("OMNICORE_STATION_ID"),
        help="stable Control Station UUID; derived from host and user by default",
    )

    groups = parser.add_subparsers(dest="group", required=True)
    _add_controller_commands(groups)
    _add_rapid_commands(groups)
    _add_io_commands(groups)
    _add_cfg_commands(groups)
    _add_file_commands(groups)
    _add_backup_commands(groups)
    _add_control_station_commands(groups)
    return parser


def _add_controller_commands(groups: argparse._SubParsersAction) -> None:
    controller = groups.add_parser("controller", help="controller information")
    commands = controller.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="show current controller status")
    status.add_argument("--json", action="store_true", dest="as_json")
    restart = commands.add_parser("restart", help="request a warm controller restart")
    restart.add_argument("--yes", action="store_true", help="confirm warm restart")
    restart.add_argument(
        "--allow-running",
        action="store_true",
        help="allow restart while RAPID is not stopped",
    )
    restart.add_argument("--json", action="store_true", dest="as_json")


def _add_rapid_commands(groups: argparse._SubParsersAction) -> None:
    rapid = groups.add_parser("rapid", help="RAPID program information")
    commands = rapid.add_subparsers(dest="command", required=True)
    tasks = commands.add_parser("tasks", help="list RAPID tasks")
    tasks.add_argument("--json", action="store_true", dest="as_json")
    modules = commands.add_parser("modules", help="list modules in a RAPID task")
    modules.add_argument("task", help="RAPID task name, for example T_ROB1")
    modules.add_argument("--json", action="store_true", dest="as_json")
    read = commands.add_parser("read", help="write RAPID module source to stdout")
    read.add_argument("task", help="RAPID task name, for example T_ROB1")
    read.add_argument("module", help="RAPID module name")
    read.add_argument("--json", action="store_true", dest="as_json")


def _add_io_commands(groups: argparse._SubParsersAction) -> None:
    io_group = groups.add_parser("io", help="I/O system information")
    commands = io_group.add_subparsers(dest="command", required=True)
    networks = commands.add_parser("networks", help="list I/O networks")
    networks.add_argument("--json", action="store_true", dest="as_json")
    devices = commands.add_parser("devices", help="list devices on an I/O network")
    devices.add_argument("network", help="I/O network name, for example EtherCAT")
    devices.add_argument("--json", action="store_true", dest="as_json")
    signals = commands.add_parser("signals", help="list or search I/O signals")
    signals.add_argument("--network")
    signals.add_argument("--device")
    signals.add_argument(
        "--type",
        dest="signal_type",
        choices=("DI", "DO", "AI", "AO", "GI", "GO"),
    )
    signals.add_argument("--name")
    signals.add_argument("--json", action="store_true", dest="as_json")
    io_get = commands.add_parser("get", help="read one I/O signal")
    io_get.add_argument("network")
    io_get.add_argument("device")
    io_get.add_argument("name")
    io_get.add_argument("--json", action="store_true", dest="as_json")


def _add_cfg_commands(groups: argparse._SubParsersAction) -> None:
    cfg = groups.add_parser("cfg", help="controller configuration database")
    commands = cfg.add_subparsers(dest="command", required=True)
    domains = commands.add_parser("domains", help="list CFG domains")
    domains.add_argument("--json", action="store_true", dest="as_json")
    cfg_types = commands.add_parser("types", help="list types in a CFG domain")
    cfg_types.add_argument("domain", help="CFG domain, for example EIO")
    cfg_types.add_argument("--json", action="store_true", dest="as_json")
    instances = commands.add_parser("instances", help="list CFG type instances")
    instances.add_argument("domain")
    instances.add_argument("cfg_type")
    instances.add_argument("--json", action="store_true", dest="as_json")
    cfg_get = commands.add_parser("get", help="read one CFG instance")
    cfg_get.add_argument("domain")
    cfg_get.add_argument("cfg_type")
    cfg_get.add_argument("instance")
    cfg_get.add_argument("--json", action="store_true", dest="as_json")
    cfg_set = commands.add_parser("set", help="update one CFG instance attribute")
    cfg_set.add_argument("domain")
    cfg_set.add_argument("cfg_type")
    cfg_set.add_argument("instance")
    cfg_set.add_argument("attribute")
    cfg_set.add_argument("value")
    cfg_set.add_argument("--element-count", type=_positive_int, default=1)
    cfg_set.add_argument("--yes", action="store_true", help="confirm CFG mutation")
    cfg_set.add_argument("--json", action="store_true", dest="as_json")


def _add_file_commands(groups: argparse._SubParsersAction) -> None:
    files = groups.add_parser("file", help="controller file service")
    commands = files.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser("list", aliases=["ls"], help="list a directory")
    list_command.add_argument("path", nargs="?", default="/")
    list_command.add_argument("--json", action="store_true", dest="as_json")
    download = commands.add_parser("download", help="download one controller file")
    download.add_argument("remote_path")
    download.add_argument("local_path")
    download.add_argument("--force", action="store_true")
    download.add_argument("--json", action="store_true", dest="as_json")
    upload = commands.add_parser("upload", help="upload one local file")
    upload.add_argument("local_path")
    upload.add_argument("remote_path")
    upload.add_argument("--force", action="store_true")
    upload.add_argument("--json", action="store_true", dest="as_json")
    delete = commands.add_parser("delete", help="delete one controller file")
    delete.add_argument("remote_path")
    delete.add_argument(
        "--yes",
        action="store_true",
        help="confirm permanent deletion",
    )
    delete.add_argument("--json", action="store_true", dest="as_json")


def _add_backup_commands(groups: argparse._SubParsersAction) -> None:
    backup = groups.add_parser("backup", help="controller backup operations")
    commands = backup.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="show controller backup state")
    status.add_argument("--json", action="store_true", dest="as_json")
    create = commands.add_parser("create", help="create and wait for a backup")
    create.add_argument("destination", help="controller path, for example $TEMP/name")
    create.add_argument(
        "--directory",
        action="store_false",
        dest="archive",
        help="create a directory backup instead of the default tar archive",
    )
    create.add_argument(
        "--force",
        action="store_true",
        help="allow the controller to replace an existing destination",
    )
    create.add_argument(
        "--allow-running",
        action="store_true",
        help="allow backup while RAPID is not stopped",
    )
    create.add_argument(
        "--wait-timeout",
        type=_positive_float,
        default=300.0,
        metavar="SECONDS",
    )
    create.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=1.0,
        metavar="SECONDS",
    )
    create.add_argument("--json", action="store_true", dest="as_json")


def _add_control_station_commands(groups: argparse._SubParsersAction) -> None:
    station = groups.add_parser(
        "controlstation", help="RobotWare 8 Control Station state"
    )
    commands = station.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="show remote write-access state")
    status.add_argument("--json", action="store_true", dest="as_json")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
            return _dispatch(client, args)
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


def _dispatch(client: RwsClient, args: argparse.Namespace) -> int:
    command = (args.group, args.command)
    if command == ("controller", "status"):
        print(format_status(ControllerService(client).status(), as_json=args.as_json))
    elif command == ("controller", "restart"):
        if not args.yes:
            raise ConfigurationError(
                "controller restart requires explicit --yes confirmation"
            )
        controller = ControllerService(client)
        status = controller.status()
        if not args.allow_running and status.rapid_execution.lower() != "stopped":
            raise ConfigurationError(
                "RAPID is not stopped; stop it or explicitly use --allow-running"
            )
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(
            station, best_effort_release=True
        ):
            result = controller.warm_restart()
        print(format_restart_result(result, as_json=args.as_json))
    elif command == ("rapid", "tasks"):
        print(format_tasks(RapidService(client).list_tasks(), as_json=args.as_json))
    elif command == ("rapid", "modules"):
        print(
            format_modules(
                RapidService(client).list_modules(args.task), as_json=args.as_json
            )
        )
    elif command == ("rapid", "read"):
        source = RapidService(client).get_module_source(args.task, args.module)
        write_source(source, as_json=args.as_json)
    elif command == ("io", "networks"):
        print(format_networks(IoService(client).list_networks(), as_json=args.as_json))
    elif command == ("io", "devices"):
        print(
            format_devices(
                IoService(client).list_devices(args.network), as_json=args.as_json
            )
        )
    elif command == ("io", "signals"):
        signals = IoService(client).list_signals(
            network=args.network,
            device=args.device,
            signal_type=args.signal_type,
            name=args.name,
        )
        print(format_signals(signals, as_json=args.as_json))
    elif command == ("io", "get"):
        signal = IoService(client).get_signal(args.network, args.device, args.name)
        print(format_signal_details(signal, as_json=args.as_json))
    elif command == ("cfg", "domains"):
        print(format_cfg_domains(CfgService(client).list_domains(), as_json=args.as_json))
    elif command == ("cfg", "types"):
        print(
            format_cfg_types(
                CfgService(client).list_types(args.domain), as_json=args.as_json
            )
        )
    elif command == ("cfg", "instances"):
        instances = CfgService(client).list_instances(args.domain, args.cfg_type)
        print(format_cfg_instances(instances, as_json=args.as_json))
    elif command == ("cfg", "get"):
        instance = CfgService(client).get_instance(
            args.domain, args.cfg_type, args.instance
        )
        print(format_cfg_instance(instance, as_json=args.as_json))
    elif command == ("cfg", "set"):
        if not args.yes:
            raise ConfigurationError("cfg set requires explicit --yes confirmation")
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            change = CfgService(client).set_attribute(
                args.domain,
                args.cfg_type,
                args.instance,
                args.attribute,
                args.value,
                element_count=args.element_count,
            )
        print(format_cfg_change(change, as_json=args.as_json))
    elif args.group == "file" and args.command in {"list", "ls"}:
        entries = FileService(client).list_directory(args.path)
        print(format_file_entries(entries, as_json=args.as_json))
    elif command == ("file", "download"):
        result = FileService(client).download_file(
            args.remote_path, Path(args.local_path), overwrite=args.force
        )
        print(format_download_result(result, as_json=args.as_json))
    elif command == ("file", "upload"):
        files = FileService(client)
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            result = files.upload_file(
                Path(args.local_path), args.remote_path, overwrite=args.force
            )
        print(format_upload_result(result, as_json=args.as_json))
    elif command == ("file", "delete"):
        if not args.yes:
            raise ConfigurationError("file delete requires explicit --yes confirmation")
        files = FileService(client)
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            result = files.delete_file(args.remote_path)
        print(format_delete_result(result, as_json=args.as_json))
    elif command == ("backup", "status"):
        print(format_backup_status(BackupService(client).status(), as_json=args.as_json))
    elif command == ("backup", "create"):
        if not args.allow_running:
            rapid_state = ControllerService(client).status().rapid_execution
            if rapid_state.lower() != "stopped":
                raise ConfigurationError(
                    "RAPID is not stopped; stop it or explicitly use --allow-running"
                )
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            result = BackupService(client).create(
                args.destination,
                archive=args.archive,
                overwrite=args.force,
                timeout=args.wait_timeout,
                poll_interval=args.poll_interval,
            )
        print(format_backup_result(result, as_json=args.as_json))
    elif command == ("controlstation", "status"):
        status = ControlStationService(client).status()
        print(format_write_access_status(status, as_json=args.as_json))
    else:
        raise ConfigurationError("unsupported command")
    return 0


def _password() -> str:
    password = os.getenv("OMNICORE_PASSWORD")
    if password is not None:
        return _required(password, "OMNICORE_PASSWORD")
    if not sys.stdin.isatty():
        raise ConfigurationError(
            "OMNICORE_PASSWORD is required when standard input is not interactive"
        )
    return _required(getpass.getpass("Controller password: "), "controller password")


def _remote_control_station(args: argparse.Namespace) -> RemoteControlStation:
    station_id = args.station_id
    if station_id is None:
        identity = f"{socket.gethostname()}|{args.host}|{args.username}"
        station_id = str(uuid5(UUID("5b4e01a8-87d8-4d1b-83c3-c43952738f13"), identity))
    pin = os.getenv("OMNICORE_CONTROL_STATION_PIN")
    if pin is None:
        if not sys.stdin.isatty():
            raise ConfigurationError(
                "OMNICORE_CONTROL_STATION_PIN is required for non-interactive writes"
            )
        pin = getpass.getpass("Control Station PIN: ")
    return RemoteControlStation(args.station_name, station_id, pin)


def _required(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(f"missing {label}")
    return value.strip()


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _error(exc: Exception, exit_code: int) -> int:
    print(f"omnicorectl: {exc}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
