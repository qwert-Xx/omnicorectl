"""Command-line parsing and dispatch.

命令行参数解析与命令分发。
"""

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
    format_cfg_creation,
    format_cfg_deletion,
    format_cfg_domains,
    format_cfg_instance,
    format_cfg_instances,
    format_cfg_types,
    format_delete_result,
    format_devices,
    format_download_result,
    format_file_entries,
    format_networks,
    format_restart_result,
    format_signal_details,
    format_signals,
    format_status,
    format_upload_result,
    format_write_access_status,
)
from omnicorectl.rapid_cli import (
    add_rapid_commands,
    dispatch_local_rapid,
    dispatch_rapid,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omnicorectl",
        description="Manage ABB OmniCore controllers through RWS 2.0. / "
        "通过 RWS 2.0 管理 ABB OmniCore 控制器。",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OMNICORE_HOST"),
        help="controller host or URL / 控制器主机名、IP 或 URL",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("OMNICORE_USERNAME"),
        help="controller username / 控制器用户名",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=_env_flag("OMNICORE_INSECURE"),
        help="disable TLS certificate verification; required for factory "
        "certificates / 禁用 TLS 证书校验；使用出厂证书时需要",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=os.getenv("OMNICORE_TIMEOUT", "10"),
        metavar="SECONDS",
        help="request timeout in seconds / 请求超时秒数",
    )
    parser.add_argument(
        "--station-name",
        default=os.getenv(
            "OMNICORE_STATION_NAME", f"omnicorectl@{socket.gethostname()}"
        ),
        help="RW8 remote Control Station display name for write commands / "
        "写命令使用的 RW8 远程控制站显示名称",
    )
    parser.add_argument(
        "--station-id",
        default=os.getenv("OMNICORE_STATION_ID"),
        help="stable Control Station UUID; derived from host and user by default / "
        "稳定的控制站 UUID；默认由主机和用户推导",
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
    controller = groups.add_parser(
        "controller", help="controller information / 控制器信息"
    )
    commands = controller.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status", help="show current controller status / 显示当前控制器状态"
    )
    status.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    restart = commands.add_parser(
        "restart", help="request a warm controller restart / 请求控制器暖启动"
    )
    restart.add_argument(
        "--yes", action="store_true", help="confirm warm restart / 确认暖启动"
    )
    restart.add_argument(
        "--allow-running",
        action="store_true",
        help="allow restart while RAPID is not stopped / 允许在 RAPID 未停止时重启",
    )
    restart.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _add_rapid_commands(groups: argparse._SubParsersAction) -> None:
    add_rapid_commands(groups)


def _add_io_commands(groups: argparse._SubParsersAction) -> None:
    io_group = groups.add_parser("io", help="I/O system information / I/O 系统信息")
    commands = io_group.add_subparsers(dest="command", required=True)
    networks = commands.add_parser("networks", help="list I/O networks / 列出 I/O 网络")
    networks.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    devices = commands.add_parser(
        "devices", help="list devices on an I/O network / 列出 I/O 网络上的设备"
    )
    devices.add_argument(
        "network",
        help="I/O network name, for example EtherCAT / I/O 网络名，例如 EtherCAT",
    )
    devices.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    signals = commands.add_parser(
        "signals", help="list or search I/O signals / 列出或搜索 I/O 信号"
    )
    signals.add_argument("--network", help="filter by network / 按网络筛选")
    signals.add_argument("--device", help="filter by device / 按设备筛选")
    signals.add_argument(
        "--type",
        dest="signal_type",
        choices=("DI", "DO", "AI", "AO", "GI", "GO"),
        help="filter by signal type / 按信号类型筛选",
    )
    signals.add_argument("--name", help="filter by signal name / 按信号名筛选")
    signals.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    io_get = commands.add_parser("get", help="read one I/O signal / 读取一个 I/O 信号")
    io_get.add_argument("network", help="I/O network name / I/O 网络名")
    io_get.add_argument("device", help="I/O device name / I/O 设备名")
    io_get.add_argument("name", help="I/O signal name / I/O 信号名")
    io_get.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _add_cfg_commands(groups: argparse._SubParsersAction) -> None:
    cfg = groups.add_parser(
        "cfg", help="controller configuration database / 控制器配置数据库"
    )
    commands = cfg.add_subparsers(dest="command", required=True)
    domains = commands.add_parser("domains", help="list CFG domains / 列出 CFG 域")
    domains.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    cfg_types = commands.add_parser(
        "types", help="list types in a CFG domain / 列出 CFG 域中的类型"
    )
    cfg_types.add_argument(
        "domain", help="CFG domain, for example EIO / CFG 域，例如 EIO"
    )
    cfg_types.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    instances = commands.add_parser(
        "instances", help="list CFG type instances / 列出 CFG 类型实例"
    )
    instances.add_argument("domain", help="CFG domain / CFG 域")
    instances.add_argument("cfg_type", help="CFG type / CFG 类型")
    instances.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    cfg_get = commands.add_parser(
        "get", help="read one CFG instance / 读取一个 CFG 实例"
    )
    cfg_get.add_argument("domain", help="CFG domain / CFG 域")
    cfg_get.add_argument("cfg_type", help="CFG type / CFG 类型")
    cfg_get.add_argument("instance", help="CFG instance name / CFG 实例名")
    cfg_get.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    cfg_set = commands.add_parser(
        "set", help="update one CFG instance attribute / 更新一个 CFG 实例属性"
    )
    cfg_set.add_argument("domain", help="CFG domain / CFG 域")
    cfg_set.add_argument("cfg_type", help="CFG type / CFG 类型")
    cfg_set.add_argument("instance", help="CFG instance name / CFG 实例名")
    cfg_set.add_argument("attribute", help="attribute name / 属性名")
    cfg_set.add_argument("value", help="new attribute value / 新属性值")
    cfg_set.add_argument(
        "--element-count",
        type=_positive_int,
        default=1,
        help="array element count / 数组元素数量",
    )
    cfg_set.add_argument(
        "--yes", action="store_true", help="confirm CFG mutation / 确认修改 CFG"
    )
    cfg_set.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    cfg_create = commands.add_parser(
        "create",
        help="create, configure, validate, and verify a CFG instance / "
        "创建、配置、校验并验证一个 CFG 实例",
    )
    cfg_create.add_argument("domain", help="CFG domain / CFG 域")
    cfg_create.add_argument("cfg_type", help="CFG type / CFG 类型")
    cfg_create.add_argument("instance", help="new CFG instance name / 新 CFG 实例名")
    cfg_create.add_argument(
        "--set",
        dest="attribute_assignments",
        action="append",
        default=[],
        metavar="ATTRIBUTE=VALUE",
        help="set an initial attribute; may be repeated / 设置初始属性；可重复使用",
    )
    cfg_create.add_argument(
        "--yes", action="store_true", help="confirm CFG mutation / 确认修改 CFG"
    )
    cfg_create.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    cfg_delete = commands.add_parser(
        "delete",
        help="validate, delete, and verify a CFG instance / 校验、删除并验证一个 CFG 实例",
    )
    cfg_delete.add_argument("domain", help="CFG domain / CFG 域")
    cfg_delete.add_argument("cfg_type", help="CFG type / CFG 类型")
    cfg_delete.add_argument("instance", help="CFG instance name / CFG 实例名")
    cfg_delete.add_argument(
        "--yes", action="store_true", help="confirm CFG deletion / 确认删除 CFG 实例"
    )
    cfg_delete.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _add_file_commands(groups: argparse._SubParsersAction) -> None:
    files = groups.add_parser("file", help="controller file service / 控制器文件服务")
    commands = files.add_subparsers(dest="command", required=True)
    list_command = commands.add_parser(
        "list", aliases=["ls"], help="list a directory / 列出目录内容"
    )
    list_command.add_argument(
        "path", nargs="?", default="/", help="controller directory / 控制器目录"
    )
    list_command.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    download = commands.add_parser(
        "download", help="download one controller file / 下载一个控制器文件"
    )
    download.add_argument("remote_path", help="controller file path / 控制器文件路径")
    download.add_argument("local_path", help="local destination path / 本地目标路径")
    download.add_argument(
        "--force", action="store_true", help="replace local file / 覆盖本地文件"
    )
    download.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    upload = commands.add_parser(
        "upload", help="upload one local file / 上传一个本地文件"
    )
    upload.add_argument("local_path", help="local source path / 本地源路径")
    upload.add_argument("remote_path", help="controller destination / 控制器目标路径")
    upload.add_argument(
        "--force", action="store_true", help="replace remote file / 覆盖远程文件"
    )
    upload.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    delete = commands.add_parser(
        "delete", help="delete one controller file / 删除一个控制器文件"
    )
    delete.add_argument("remote_path", help="controller file path / 控制器文件路径")
    delete.add_argument(
        "--yes",
        action="store_true",
        help="confirm permanent deletion / 确认永久删除",
    )
    delete.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _add_backup_commands(groups: argparse._SubParsersAction) -> None:
    backup = groups.add_parser(
        "backup", help="controller backup operations / 控制器备份操作"
    )
    commands = backup.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status", help="show controller backup state / 显示控制器备份状态"
    )
    status.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )
    create = commands.add_parser(
        "create", help="create and wait for a backup / 创建备份并等待完成"
    )
    create.add_argument(
        "destination",
        help="controller path, for example $TEMP/name / 控制器路径，例如 $TEMP/name",
    )
    create.add_argument(
        "--directory",
        action="store_false",
        dest="archive",
        help="create a directory backup instead of the default tar archive / "
        "创建目录备份而非默认 tar 归档",
    )
    create.add_argument(
        "--force",
        action="store_true",
        help="allow the controller to replace an existing destination / "
        "允许控制器替换已有目标",
    )
    create.add_argument(
        "--allow-running",
        action="store_true",
        help="allow backup while RAPID is not stopped / 允许在 RAPID 未停止时备份",
    )
    create.add_argument(
        "--wait-timeout",
        type=_positive_float,
        default=300.0,
        metavar="SECONDS",
        help="maximum completion wait / 最长完成等待时间",
    )
    create.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=1.0,
        metavar="SECONDS",
        help="progress polling interval / 进度轮询间隔",
    )
    create.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _add_control_station_commands(groups: argparse._SubParsersAction) -> None:
    station = groups.add_parser(
        "controlstation",
        help="RobotWare 8 Control Station state / RobotWare 8 控制站状态",
    )
    commands = station.add_subparsers(dest="command", required=True)
    status = commands.add_parser(
        "status", help="show remote write-access state / 显示远程写权限状态"
    )
    status.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        local_result = dispatch_local_rapid(args)
        if local_result is not None:
            return local_result
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
    if args.group == "rapid":
        return dispatch_rapid(client, args, lambda: _remote_control_station(args))
    if command == ("controller", "status"):
        print(format_status(ControllerService(client).status(), as_json=args.as_json))
    elif command == ("controller", "restart"):
        if not args.yes:
            raise ConfigurationError(
                "controller restart requires explicit --yes confirmation"
            )
        controller = ControllerService(client)
        controller_status = controller.status()
        if (
            not args.allow_running
            and controller_status.rapid_execution.lower() != "stopped"
        ):
            raise ConfigurationError(
                "RAPID is not stopped; stop it or explicitly use --allow-running"
            )
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(
            station, best_effort_release=True
        ):
            restart_result = controller.warm_restart()
        print(format_restart_result(restart_result, as_json=args.as_json))
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
        print(
            format_cfg_domains(CfgService(client).list_domains(), as_json=args.as_json)
        )
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
    elif command == ("cfg", "create"):
        if not args.yes:
            raise ConfigurationError("cfg create requires explicit --yes confirmation")
        attributes = _attribute_assignments(args.attribute_assignments)
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            creation = CfgService(client).create_instance(
                args.domain, args.cfg_type, args.instance, attributes
            )
        print(format_cfg_creation(creation, as_json=args.as_json))
    elif command == ("cfg", "delete"):
        if not args.yes:
            raise ConfigurationError("cfg delete requires explicit --yes confirmation")
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            deletion = CfgService(client).delete_instance(
                args.domain, args.cfg_type, args.instance
            )
        print(format_cfg_deletion(deletion, as_json=args.as_json))
    elif args.group == "file" and args.command in {"list", "ls"}:
        entries = FileService(client).list_directory(args.path)
        print(format_file_entries(entries, as_json=args.as_json))
    elif command == ("file", "download"):
        download_result = FileService(client).download_file(
            args.remote_path, Path(args.local_path), overwrite=args.force
        )
        print(format_download_result(download_result, as_json=args.as_json))
    elif command == ("file", "upload"):
        files = FileService(client)
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            upload_result = files.upload_file(
                Path(args.local_path), args.remote_path, overwrite=args.force
            )
        print(format_upload_result(upload_result, as_json=args.as_json))
    elif command == ("file", "delete"):
        if not args.yes:
            raise ConfigurationError("file delete requires explicit --yes confirmation")
        files = FileService(client)
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            delete_result = files.delete_file(args.remote_path)
        print(format_delete_result(delete_result, as_json=args.as_json))
    elif command == ("backup", "status"):
        print(
            format_backup_status(BackupService(client).status(), as_json=args.as_json)
        )
    elif command == ("backup", "create"):
        if not args.allow_running:
            rapid_state = ControllerService(client).status().rapid_execution
            if rapid_state.lower() != "stopped":
                raise ConfigurationError(
                    "RAPID is not stopped; stop it or explicitly use --allow-running"
                )
        station = _remote_control_station(args)
        with ControlStationService(client).write_access(station):
            backup_result = BackupService(client).create(
                args.destination,
                archive=args.archive,
                overwrite=args.force,
                timeout=args.wait_timeout,
                poll_interval=args.poll_interval,
            )
        print(format_backup_result(backup_result, as_json=args.as_json))
    elif command == ("controlstation", "status"):
        write_status = ControlStationService(client).status()
        print(format_write_access_status(write_status, as_json=args.as_json))
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


def _attribute_assignments(assignments: Sequence[str]) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for assignment in assignments:
        attribute, separator, value = assignment.partition("=")
        attribute = attribute.strip()
        if not separator or not attribute:
            raise ConfigurationError(
                f"invalid CFG attribute assignment {assignment!r}; "
                "expected ATTRIBUTE=VALUE"
            )
        if attribute in attributes:
            raise ConfigurationError(f"duplicate CFG attribute assignment: {attribute}")
        attributes[attribute] = value
    return attributes


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _error(exc: Exception, exit_code: int) -> int:
    print(f"omnicorectl: {exc}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
