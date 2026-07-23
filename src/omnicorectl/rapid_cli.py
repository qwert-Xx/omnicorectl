"""RAPID command-line surface and dispatch.

RAPID 命令行界面与分发。
"""

from __future__ import annotations

import argparse
import difflib
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from omnicorectl.errors import ConfigurationError
from omnicorectl.output import (
    format_breakpoints,
    format_build_errors,
    format_execution_state,
    format_module_attributes,
    format_module_deploy,
    format_module_write,
    format_modules,
    format_program_pointers,
    format_rapid_action,
    format_rapid_data,
    format_symbol_data,
    format_symbols,
    format_tasks,
    write_source,
)
from omnicorectl.rws import RwsClient
from omnicorectl.services.controller import ControllerService
from omnicorectl.services.control_station import (
    ControlStationService,
    RemoteControlStation,
)
from omnicorectl.services.files import FileService
from omnicorectl.services.rapid import RapidService
from omnicorectl.services.rapid_debug import RapidDebugService
from omnicorectl.services.rapid_editing import (
    RapidEditingService,
    validate_module_source,
)

StationFactory = Callable[[], RemoteControlStation]


def add_rapid_commands(groups: argparse._SubParsersAction) -> None:
    rapid = groups.add_parser(
        "rapid", help="RAPID source, deployment, and debugging / RAPID 源码、部署与调试"
    )
    commands = rapid.add_subparsers(dest="command", required=True)

    tasks = commands.add_parser("tasks", help="list RAPID tasks / 列出 RAPID 任务")
    _json_option(tasks)
    modules = commands.add_parser(
        "modules", help="list modules in a RAPID task / 列出 RAPID 任务中的模块"
    )
    modules.add_argument("task", help="RAPID task / RAPID 任务")
    _json_option(modules)

    read = commands.add_parser("read", help="read a complete module / 读取完整模块")
    read.add_argument("task")
    read.add_argument("module")
    read.add_argument(
        "--output", metavar="FILE", help="write source to a local file / 写入本地文件"
    )
    read.add_argument(
        "--force", action="store_true", help="replace the output file / 覆盖输出文件"
    )
    _json_option(read)

    validate = commands.add_parser(
        "validate", help="validate a local module before upload / 上传前校验本地模块"
    )
    validate.add_argument("file")
    validate.add_argument("--expected-module")
    _json_option(validate)

    info = commands.add_parser(
        "module-info", help="show module attributes and size / 显示模块属性与尺寸"
    )
    info.add_argument("task")
    info.add_argument("module")
    _json_option(info)

    read_range = commands.add_parser(
        "read-range", help="read a source range / 读取源码范围"
    )
    _source_range_arguments(read_range, allow_end_of_line=True)
    _json_option(read_range)

    search = commands.add_parser(
        "search", help="search text in a module / 在模块中搜索文本"
    )
    search.add_argument("task")
    search.add_argument("module")
    search.add_argument("text")
    search.add_argument("--start-row", type=_positive_int, default=1)
    search.add_argument("--start-column", type=_non_negative_int, default=1)
    _json_option(search)

    write = commands.add_parser(
        "write", help="replace a complete module safely / 安全替换完整模块"
    )
    write.add_argument("task")
    write.add_argument("module")
    write.add_argument(
        "file",
        help="UTF-8 source file or '-' for stdin / UTF-8 源文件，或用 '-' 读取标准输入",
    )
    write.add_argument("--allow-rename", action="store_true")
    write.add_argument(
        "--backup",
        metavar="FILE",
        help="save the previous source locally / 在本地保存原源码",
    )
    write.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and show diff only / 仅校验并显示差异",
    )
    _edit_safety_options(write)

    edit = commands.add_parser(
        "edit", help="edit a module with $EDITOR / 使用 $EDITOR 编辑模块"
    )
    edit.add_argument("task")
    edit.add_argument("module")
    edit.add_argument(
        "--editor", help="editor command; defaults to $VISUAL or $EDITOR / 编辑器命令"
    )
    edit.add_argument("--allow-rename", action="store_true")
    edit.add_argument("--backup", metavar="FILE")
    edit.add_argument("--dry-run", action="store_true")
    _edit_safety_options(edit)

    patch = commands.add_parser(
        "patch", help="insert or replace a source range / 插入或替换源码范围"
    )
    _source_range_arguments(patch)
    patch.add_argument(
        "--mode", choices=("Before", "After", "Replace"), default="Replace"
    )
    patch.add_argument("--query-mode", choices=("Force", "Try"), default="Force")
    content = patch.add_mutually_exclusive_group(required=True)
    content.add_argument("--text", help="replacement text / 替换文本")
    content.add_argument("--file", help="UTF-8 replacement file / UTF-8 替换文件")
    _edit_safety_options(patch)

    load = commands.add_parser(
        "load", help="load a controller module file / 加载控制器模块文件"
    )
    load.add_argument("task")
    load.add_argument("module_path")
    load.add_argument("--replace", action="store_true")
    _write_options(load, allow_running=True)

    unload = commands.add_parser("unload", help="unload a module / 卸载模块")
    unload.add_argument("task")
    unload.add_argument("module")
    _write_options(unload, allow_running=True)

    save = commands.add_parser(
        "save",
        help="save a loaded module to a controller file / 将已加载模块保存到控制器文件",
    )
    save.add_argument("task")
    save.add_argument("module")
    save.add_argument("path")
    save.add_argument("--name")
    _write_options(save)

    build = commands.add_parser(
        "build", help="link a RAPID task and report errors / 链接 RAPID 任务并报告错误"
    )
    build.add_argument("task")
    _write_options(build, allow_running=True)

    errors = commands.add_parser(
        "errors", help="list RAPID build errors / 列出 RAPID 构建错误"
    )
    errors.add_argument("task")
    _json_option(errors)

    deploy = commands.add_parser(
        "deploy",
        help="upload, load, build, and verify a module / 上传、加载、构建并验证模块",
    )
    deploy.add_argument("task")
    deploy.add_argument("file")
    deploy.add_argument(
        "--remote-path", help="controller staging path / 控制器暂存路径"
    )
    deploy.add_argument("--replace", action="store_true")
    deploy.add_argument("--keep-upload", action="store_true")
    deploy.add_argument("--dry-run", action="store_true")
    _edit_safety_options(deploy, change_count=False)

    program = commands.add_parser(
        "program", help="whole-program operations / 完整程序操作"
    )
    program_commands = program.add_subparsers(dest="operation", required=True)
    _program_commands(program_commands)

    execution = commands.add_parser(
        "execution", help="show RAPID execution state / 显示 RAPID 执行状态"
    )
    _json_option(execution)
    start = commands.add_parser(
        "start", help="start or step RAPID execution / 启动或单步执行 RAPID"
    )
    start.add_argument(
        "--mode",
        choices=(
            "continue",
            "stepin",
            "stepover",
            "stepout",
            "stepback",
            "steplast",
            "stepmotion",
        ),
        default="continue",
    )
    start.add_argument("--cycle", choices=("forever", "asis", "once"), default="asis")
    start.add_argument("--ignore-breakpoints", action="store_true")
    start.add_argument("--all-tasks", action="store_true")
    _write_options(start)
    stop = commands.add_parser("stop", help="stop RAPID execution / 停止 RAPID 执行")
    stop.add_argument(
        "--mode", choices=("cycle", "instr", "stop", "qstop"), default="stop"
    )
    stop.add_argument("--all-tasks", action="store_true")
    _write_options(stop)
    reset_pp = commands.add_parser(
        "reset-pp",
        help="reset all program pointers to main / 将所有程序指针复位到 main",
    )
    _write_options(reset_pp)

    pp = commands.add_parser("pp", help="program-pointer operations / 程序指针操作")
    pp_commands = pp.add_subparsers(dest="operation", required=True)
    _program_pointer_commands(pp_commands)

    breakpoint = commands.add_parser(
        "breakpoint", help="breakpoint operations / 断点操作"
    )
    breakpoint_commands = breakpoint.add_subparsers(dest="operation", required=True)
    _breakpoint_commands(breakpoint_commands)

    symbol = commands.add_parser(
        "symbol",
        help="RAPID symbol and online-data operations / RAPID 符号与在线数据操作",
    )
    symbol_commands = symbol.add_subparsers(dest="operation", required=True)
    _symbol_commands(symbol_commands)

    motion = commands.add_parser(
        "motion", help="read current RAPID motion targets / 读取当前 RAPID 运动目标"
    )
    motion_commands = motion.add_subparsers(dest="operation", required=True)
    _motion_commands(motion_commands)

    sync_status = commands.add_parser(
        "sync-pers-status",
        help="show persistent-data synchronization / 显示持久数据同步状态",
    )
    sync_status.add_argument("task")
    sync_status.add_argument("module")
    _json_option(sync_status)
    sync = commands.add_parser(
        "sync-pers", help="synchronize persistent data / 同步持久数据"
    )
    sync.add_argument("task")
    sync.add_argument("module")
    _write_options(sync)

    possible = commands.add_parser(
        "modifiable-positions",
        help="find modifiable motion positions / 查找可修改运动位置",
    )
    _source_range_arguments(possible)
    _json_option(possible)
    modify = commands.add_parser(
        "modify-position",
        help="update a robtarget from the current robot position / 使用机器人当前位置更新 robtarget",
    )
    _source_range_arguments(modify)
    modify.add_argument("--skip-limit-check", action="store_true")
    modify.add_argument("--skip-deactivated-axis-check", action="store_true")
    modify.add_argument("--allow-deactivated-axes", action="store_true")
    _write_options(modify)

    activate = commands.add_parser(
        "activate-task", help="activate a RAPID task / 激活 RAPID 任务"
    )
    activate.add_argument("task")
    _write_options(activate)
    deactivate = commands.add_parser(
        "deactivate-task", help="deactivate a RAPID task / 停用 RAPID 任务"
    )
    deactivate.add_argument("task")
    _write_options(deactivate)


def dispatch_local_rapid(args: argparse.Namespace) -> int | None:
    """Run RAPID commands that deliberately require no controller session.

    执行明确不需要控制器会话的 RAPID 命令。
    """

    if args.group != "rapid" or args.command != "validate":
        return None
    validation = validate_module_source(
        _read_utf8(Path(args.file)), expected_module=args.expected_module
    )
    print(format_rapid_data(validation, as_json=args.as_json))
    return 0


def dispatch_rapid(
    client: RwsClient, args: argparse.Namespace, station_factory: StationFactory
) -> int:
    rapid = RapidService(client)
    debug = RapidDebugService(client)
    command = args.command

    if command == "tasks":
        print(format_tasks(rapid.list_tasks(), as_json=args.as_json))
    elif command == "modules":
        print(format_modules(rapid.list_modules(args.task), as_json=args.as_json))
    elif command == "read":
        source = rapid.get_module_source(args.task, args.module)
        if args.output:
            _write_local_text(Path(args.output), source.source, overwrite=args.force)
            print(format_rapid_data(source, as_json=args.as_json))
        else:
            write_source(source, as_json=args.as_json)
    elif command == "module-info":
        attributes = rapid.get_module_attributes(args.task, args.module)
        extension = rapid.get_module_extension(args.task, args.module)
        if args.as_json:
            print(
                format_rapid_data(
                    {"attributes": attributes, "extension": extension}, as_json=True
                )
            )
        else:
            print(format_module_attributes(attributes, as_json=False))
            print(format_rapid_data(extension, as_json=False))
    elif command == "read-range":
        text_range = rapid.get_text_range(args.task, args.module, **_range_values(args))
        if args.as_json:
            print(format_rapid_data(text_range, as_json=True))
        else:
            sys.stdout.write(text_range.text)
            if not text_range.text.endswith("\n"):
                sys.stdout.write("\n")
    elif command == "search":
        position = rapid.search_text(
            args.task,
            args.module,
            args.text,
            start_row=args.start_row,
            start_column=args.start_column,
        )
        if position is None:
            print("null" if args.as_json else "Text not found.")
        else:
            print(format_rapid_data(position, as_json=args.as_json))
    elif command in {"write", "edit"}:
        _dispatch_source_edit(client, rapid, args, station_factory)
    elif command == "patch":
        _ensure_yes(args)
        _ensure_stopped(client, args)
        text = args.text if args.text is not None else _read_utf8(Path(args.file))
        with _write_access(client, station_factory):
            write_result = RapidEditingService(rapid).patch_module(
                args.task,
                args.module,
                replace_mode=args.mode,
                text=text,
                query_mode=args.query_mode,
                expected_change_count=args.if_change_count,
                build=not args.no_build,
                rollback_on_error=not args.no_rollback,
                **_range_values(args),
            )
        print(format_module_write(write_result, as_json=args.as_json))
    elif command == "load":
        _ensure_yes(args)
        _ensure_stopped(client, args)
        with _write_access(client, station_factory):
            load_result = rapid.load_module(
                args.task, args.module_path, replace=args.replace
            )
        print(format_rapid_data(load_result, as_json=args.as_json))
    elif command == "unload":
        _ensure_yes(args)
        _ensure_stopped(client, args)
        with _write_access(client, station_factory):
            action = rapid.unload_module(args.task, args.module)
        print(format_rapid_action(action, as_json=args.as_json))
    elif command == "save":
        _ensure_yes(args)
        with _write_access(client, station_factory):
            action = rapid.save_module(
                args.task, args.module, path=args.path, name=args.name
            )
        print(format_rapid_action(action, as_json=args.as_json))
    elif command == "build":
        _ensure_yes(args)
        _ensure_stopped(client, args)
        with _write_access(client, station_factory):
            rapid.build_task(args.task)
            errors = rapid.get_build_errors(args.task)
        print(format_build_errors(errors, as_json=args.as_json))
        return 7 if errors else 0
    elif command == "errors":
        print(
            format_build_errors(rapid.get_build_errors(args.task), as_json=args.as_json)
        )
    elif command == "deploy":
        _dispatch_deploy(client, rapid, args, station_factory)
    elif command == "program":
        _dispatch_program(client, rapid, args, station_factory)
    elif command == "execution":
        print(format_execution_state(debug.execution_state(), as_json=args.as_json))
    elif command in {"start", "stop", "reset-pp"}:
        _dispatch_execution(client, debug, args, station_factory)
    elif command == "pp":
        _dispatch_program_pointer(client, debug, args, station_factory)
    elif command == "breakpoint":
        _dispatch_breakpoint(client, debug, args, station_factory)
    elif command == "symbol":
        _dispatch_symbol(client, debug, args, station_factory)
    elif command == "motion":
        if args.operation == "mechunits":
            print(
                format_rapid_data(
                    debug.list_mechanical_units(args.task), as_json=args.as_json
                )
            )
        elif args.operation == "robtarget":
            print(
                format_rapid_data(
                    debug.get_robot_target(
                        args.task, tool=args.tool, work_object=args.work_object
                    ),
                    as_json=args.as_json,
                )
            )
        elif args.operation == "jointtarget":
            print(
                format_rapid_data(
                    debug.get_joint_target(args.task), as_json=args.as_json
                )
            )
        else:
            raise ConfigurationError(
                f"unsupported RAPID motion command: {args.operation}"
            )
    elif command == "sync-pers-status":
        synchronized = rapid.persistent_data_is_synchronized(args.task, args.module)
        print(
            format_rapid_data(
                {
                    "task": args.task,
                    "module": args.module,
                    "synchronized": synchronized,
                },
                as_json=args.as_json,
            )
        )
    elif command == "sync-pers":
        _ensure_yes(args)
        with _write_access(client, station_factory):
            action = rapid.sync_persistent_data(args.task, args.module)
        print(format_rapid_action(action, as_json=args.as_json))
    elif command == "modifiable-positions":
        modifiable = rapid.get_modifiable_positions(
            args.task, args.module, **_range_values(args)
        )
        print(format_rapid_data(modifiable, as_json=args.as_json))
    elif command == "modify-position":
        _ensure_yes(args)
        with _write_access(client, station_factory):
            action = rapid.modify_position(
                args.task,
                args.module,
                check_limits=not args.skip_limit_check,
                check_deactivated_axes=not args.skip_deactivated_axis_check,
                allow_deactivated_axes=args.allow_deactivated_axes,
                **_range_values(args),
            )
        print(format_rapid_action(action, as_json=args.as_json))
    elif command in {"activate-task", "deactivate-task"}:
        _ensure_yes(args)
        with _write_access(client, station_factory):
            action = (
                rapid.activate_task(args.task)
                if command == "activate-task"
                else rapid.deactivate_task(args.task)
            )
        print(format_rapid_action(action, as_json=args.as_json))
    else:
        raise ConfigurationError(f"unsupported RAPID command: {command}")
    return 0


def _dispatch_source_edit(
    client: RwsClient,
    rapid: RapidService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    original = rapid.get_module_source(args.task, args.module)
    if args.command == "write":
        source = sys.stdin.read() if args.file == "-" else _read_utf8(Path(args.file))
    else:
        source = _run_editor(original.source, args.editor, args.module)
    validate_module_source(
        source, expected_module=None if args.allow_rename else args.module
    )
    diff = _source_diff(original.source, source, args.module)
    if (
        args.if_change_count is not None
        and args.if_change_count != original.change_count
    ):
        raise ConfigurationError(
            f"RAPID module changed concurrently: {args.task}/{args.module} expected "
            f"change count {args.if_change_count}, current value is "
            f"{original.change_count}"
        )
    if args.dry_run:
        print(diff or "No changes.")
        return
    _ensure_yes(args)
    if not diff:
        result = RapidEditingService(rapid).write_module(
            args.task,
            args.module,
            source,
            expected_change_count=(
                args.if_change_count
                if args.if_change_count is not None
                else original.change_count
            ),
        )
        print(format_module_write(result, as_json=args.as_json))
        return
    if args.backup:
        _write_local_text(Path(args.backup), original.source, overwrite=False)
    _ensure_stopped(client, args)
    if not args.as_json:
        print(diff)
    with _write_access(client, station_factory):
        result = RapidEditingService(rapid).write_module(
            args.task,
            args.module,
            source,
            expected_change_count=(
                args.if_change_count
                if args.if_change_count is not None
                else original.change_count
            ),
            build=not args.no_build,
            rollback_on_error=not args.no_rollback,
            allow_rename=args.allow_rename,
        )
    print(format_module_write(result, as_json=args.as_json))


def _dispatch_deploy(
    client: RwsClient,
    rapid: RapidService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    local = Path(args.file).expanduser().resolve()
    source = _read_utf8(local)
    validation = validate_module_source(source)
    remote_path = args.remote_path or f"$TEMP/{local.name}"
    if args.dry_run:
        print(
            format_rapid_data(
                {
                    "task": args.task,
                    "module": validation.module_name,
                    "local_path": str(local),
                    "remote_path": remote_path,
                    "replace": args.replace,
                    "dry_run": True,
                },
                as_json=args.as_json,
            )
        )
        return
    _ensure_yes(args)
    _ensure_stopped(client, args)
    with _write_access(client, station_factory):
        result = RapidEditingService(rapid, FileService(client)).deploy_module(
            args.task,
            local,
            remote_path,
            replace=args.replace,
            build=not args.no_build,
            rollback_on_error=not args.no_rollback,
            remove_upload=not args.keep_upload,
        )
    print(format_module_deploy(result, as_json=args.as_json))


def _dispatch_program(
    client: RwsClient,
    rapid: RapidService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    operation = args.operation
    if operation == "info":
        print(format_rapid_data(rapid.get_program(args.task), as_json=args.as_json))
        return
    _ensure_yes(args)
    if operation in {"load", "unload"}:
        _ensure_stopped(client, args)
    with _write_access(client, station_factory):
        if operation == "load":
            result = rapid.load_program(
                args.task, args.program_path, replace=args.replace
            )
        elif operation == "unload":
            result = rapid.unload_program(args.task)
        elif operation == "save":
            result = rapid.save_program(args.task, args.path)
        elif operation == "set-name":
            result = rapid.set_program_name(args.task, args.name)
        elif operation == "set-entrypoint":
            result = rapid.set_entry_point(args.task, args.routine)
        else:
            raise ConfigurationError(f"unsupported RAPID program command: {operation}")
    print(format_rapid_action(result, as_json=args.as_json))


def _dispatch_execution(
    client: RwsClient,
    debug: RapidDebugService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    _ensure_yes(args)
    with _write_access(client, station_factory):
        if args.command == "start":
            result = debug.start_execution(
                execution_mode=args.mode,
                cycle=args.cycle,
                stop_at_breakpoint=not args.ignore_breakpoints,
                all_tasks_by_task_panel=args.all_tasks,
            )
        elif args.command == "stop":
            result = debug.stop_execution(stop_mode=args.mode, all_tasks=args.all_tasks)
        else:
            result = debug.reset_all_program_pointers()
    print(format_rapid_action(result, as_json=args.as_json))


def _dispatch_program_pointer(
    client: RwsClient,
    debug: RapidDebugService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    if args.operation == "list":
        print(
            format_program_pointers(
                debug.get_program_pointers(args.task), as_json=args.as_json
            )
        )
        return
    _ensure_yes(args)
    with _write_access(client, station_factory):
        if args.operation == "cursor":
            result = debug.set_program_pointer_cursor(
                args.task, args.module, args.line, args.column
            )
        elif args.operation == "routine":
            result = debug.set_program_pointer_routine(
                args.task, args.module, args.routine, user_level=args.user_level
            )
        elif args.operation in {"next", "previous"}:
            result = debug.move_program_pointer(args.task, args.operation)
        elif args.operation == "reset":
            result = debug.reset_program_pointer(args.task)
        else:
            raise ConfigurationError(f"unsupported RAPID PP command: {args.operation}")
    print(format_rapid_action(result, as_json=args.as_json))


def _dispatch_breakpoint(
    client: RwsClient,
    debug: RapidDebugService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    if args.operation == "list":
        print(
            format_breakpoints(debug.list_breakpoints(args.task), as_json=args.as_json)
        )
        return
    _ensure_yes(args)
    with _write_access(client, station_factory):
        if args.operation == "set":
            breakpoint = debug.set_breakpoint(
                args.task, args.module, args.row, args.column
            )
            print(format_rapid_data(breakpoint, as_json=args.as_json))
            return
        action = debug.clear_breakpoint(
            args.task,
            module=args.module,
            row=args.row,
            column=args.column,
            all_breakpoints=args.all,
        )
    print(format_rapid_action(action, as_json=args.as_json))


def _dispatch_symbol(
    client: RwsClient,
    debug: RapidDebugService,
    args: argparse.Namespace,
    station_factory: StationFactory,
) -> None:
    if args.operation == "search":
        symbols = debug.search_symbols(
            block_url=args.block_url,
            regular_expression=args.regexp,
            symbol_type=args.symbol_type,
            data_type=args.data_type,
            recursive=not args.no_recursive,
        )
        print(format_symbols(symbols, as_json=args.as_json))
    elif args.operation == "get":
        print(
            format_symbol_data(
                debug.get_symbol_data(args.symbol_url), as_json=args.as_json
            )
        )
    elif args.operation == "set":
        _ensure_yes(args)
        with _write_access(client, station_factory):
            action = debug.set_symbol_data(
                args.symbol_url,
                args.value,
                initial_value=args.initial_value,
                log_change=args.log,
            )
        print(format_rapid_action(action, as_json=args.as_json))
    elif args.operation == "validate":
        action = debug.validate_symbol_value(args.task, args.data_type, args.value)
        print(format_rapid_action(action, as_json=args.as_json))
    else:
        raise ConfigurationError(f"unsupported RAPID symbol command: {args.operation}")


def _program_commands(commands: argparse._SubParsersAction) -> None:
    info = commands.add_parser("info")
    info.add_argument("task")
    _json_option(info)
    load = commands.add_parser("load")
    load.add_argument("task")
    load.add_argument("program_path")
    load.add_argument("--replace", action="store_true")
    _write_options(load, allow_running=True)
    unload = commands.add_parser("unload")
    unload.add_argument("task")
    _write_options(unload, allow_running=True)
    save = commands.add_parser("save")
    save.add_argument("task")
    save.add_argument("path")
    _write_options(save)
    name = commands.add_parser("set-name")
    name.add_argument("task")
    name.add_argument("name")
    _write_options(name)
    entry = commands.add_parser("set-entrypoint")
    entry.add_argument("task")
    entry.add_argument("routine")
    _write_options(entry)


def _program_pointer_commands(commands: argparse._SubParsersAction) -> None:
    listing = commands.add_parser("list")
    listing.add_argument("task")
    _json_option(listing)
    cursor = commands.add_parser("cursor")
    cursor.add_argument("task")
    cursor.add_argument("module")
    cursor.add_argument("line", type=_positive_int)
    cursor.add_argument("column", type=_non_negative_int)
    _write_options(cursor)
    routine = commands.add_parser("routine")
    routine.add_argument("task")
    routine.add_argument("module")
    routine.add_argument("routine")
    routine.add_argument("--user-level", action="store_true")
    _write_options(routine)
    for operation in ("next", "previous", "reset"):
        command = commands.add_parser(operation)
        command.add_argument("task")
        _write_options(command)


def _breakpoint_commands(commands: argparse._SubParsersAction) -> None:
    listing = commands.add_parser("list")
    listing.add_argument("task")
    _json_option(listing)
    set_command = commands.add_parser("set")
    set_command.add_argument("task")
    set_command.add_argument("module")
    set_command.add_argument("row", type=_positive_int)
    set_command.add_argument("column", type=_non_negative_int)
    _write_options(set_command)
    clear = commands.add_parser("clear")
    clear.add_argument("task")
    clear.add_argument("module", nargs="?")
    clear.add_argument("row", nargs="?", type=_positive_int)
    clear.add_argument("column", nargs="?", type=_non_negative_int)
    clear.add_argument("--all", action="store_true")
    _write_options(clear)


def _symbol_commands(commands: argparse._SubParsersAction) -> None:
    search = commands.add_parser("search")
    search.add_argument(
        "block_url", help="for example RAPID/T_ROB1 / 例如 RAPID/T_ROB1"
    )
    search.add_argument("--regexp", default=".*")
    search.add_argument("--symbol-type", default="any")
    search.add_argument("--data-type")
    search.add_argument("--no-recursive", action="store_true")
    _json_option(search)
    get = commands.add_parser("get")
    get.add_argument("symbol_url")
    _json_option(get)
    set_command = commands.add_parser("set")
    set_command.add_argument("symbol_url")
    set_command.add_argument("value")
    set_command.add_argument("--initial-value", action="store_true")
    set_command.add_argument("--log", action="store_true")
    _write_options(set_command)
    validate = commands.add_parser("validate")
    validate.add_argument("task")
    validate.add_argument("data_type")
    validate.add_argument("value")
    _json_option(validate)


def _motion_commands(commands: argparse._SubParsersAction) -> None:
    units = commands.add_parser("mechunits")
    units.add_argument("task")
    _json_option(units)
    robot_target = commands.add_parser("robtarget")
    robot_target.add_argument("task")
    robot_target.add_argument("--tool")
    robot_target.add_argument("--work-object")
    _json_option(robot_target)
    joint_target = commands.add_parser("jointtarget")
    joint_target.add_argument("task")
    _json_option(joint_target)


def _source_range_arguments(
    parser: argparse.ArgumentParser, *, allow_end_of_line: bool = False
) -> None:
    parser.add_argument("task")
    parser.add_argument("module")
    parser.add_argument("start_row", type=_positive_int)
    parser.add_argument("start_column", type=_positive_int)
    parser.add_argument("end_row", type=_positive_int)
    parser.add_argument(
        "end_column", type=_end_column if allow_end_of_line else _positive_int
    )


def _range_values(args: argparse.Namespace) -> dict[str, int]:
    return {
        "start_row": args.start_row,
        "start_column": args.start_column,
        "end_row": args.end_row,
        "end_column": args.end_column,
    }


def _edit_safety_options(
    parser: argparse.ArgumentParser, *, change_count: bool = True
) -> None:
    if change_count:
        parser.add_argument("--if-change-count", type=_non_negative_int)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--no-rollback", action="store_true")
    _write_options(parser, allow_running=True)


def _write_options(
    parser: argparse.ArgumentParser, *, allow_running: bool = False
) -> None:
    parser.add_argument(
        "--yes", action="store_true", help="confirm mutation / 确认修改"
    )
    if allow_running:
        parser.add_argument(
            "--allow-running",
            action="store_true",
            help="allow while RAPID runs / 允许 RAPID 运行时操作",
        )
    _json_option(parser)


def _json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="emit JSON / 输出 JSON"
    )


def _ensure_yes(args: argparse.Namespace) -> None:
    if not args.yes:
        raise ConfigurationError(
            f"rapid {args.command} requires explicit --yes confirmation"
        )


def _ensure_stopped(client: RwsClient, args: argparse.Namespace) -> None:
    if getattr(args, "allow_running", False):
        return
    state = ControllerService(client).status().rapid_execution
    if state.lower() != "stopped":
        raise ConfigurationError(
            "RAPID is not stopped; stop it or explicitly use --allow-running"
        )


@contextmanager
def _write_access(client: RwsClient, factory: StationFactory) -> Iterator[object]:
    with ControlStationService(client).write_access(
        factory(), best_effort_release=True
    ) as status:
        yield status


def _read_utf8(path: Path) -> str:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise ConfigurationError(f"local RAPID source does not exist: {source}")
    try:
        return source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"RAPID source is not valid UTF-8: {source}") from exc
    except OSError as exc:
        raise ConfigurationError(f"cannot read RAPID source {source}: {exc}") from exc


def _write_local_text(path: Path, text: str, *, overwrite: bool) -> None:
    destination = path.expanduser().resolve()
    if not destination.parent.is_dir():
        raise ConfigurationError(
            f"destination directory does not exist: {destination.parent}"
        )
    mode = "w" if overwrite else "x"
    try:
        with destination.open(mode, encoding="utf-8", newline="") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise ConfigurationError(f"destination already exists: {destination}") from exc
    except OSError as exc:
        raise ConfigurationError(f"cannot write {destination}: {exc}") from exc


def _run_editor(source: str, editor: str | None, module: str) -> str:
    editor_command = editor or os.getenv("VISUAL") or os.getenv("EDITOR")
    if not editor_command:
        raise ConfigurationError("rapid edit requires --editor, $VISUAL, or $EDITOR")
    arguments = shlex.split(editor_command)
    if not arguments:
        raise ConfigurationError("editor command cannot be empty")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f"{module}.", suffix=".mod", delete=False
        ) as temporary:
            temporary.write(source)
            temporary_path = Path(temporary.name)
        try:
            completed = subprocess.run([*arguments, str(temporary_path)], check=False)
        except OSError as exc:
            raise ConfigurationError(f"cannot start editor: {exc}") from exc
        if completed.returncode != 0:
            raise ConfigurationError(
                f"editor exited with status {completed.returncode}"
            )
        return _read_utf8(temporary_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _source_diff(before: str, after: str, module: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"controller/{module}",
            tofile=f"edited/{module}",
        )
    )


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number


def _end_column(value: str) -> int:
    number = int(value)
    if number == -1 or number > 0:
        return number
    raise argparse.ArgumentTypeError("must be positive or -1")
