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
from omnicorectl.services.controller import ControllerService, ControllerStatus
from omnicorectl.services.rapid import RapidModule, RapidService, RapidTask


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
