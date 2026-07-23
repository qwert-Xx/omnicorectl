"""RAPID execution, program-pointer, breakpoint, and symbol APIs.

RAPID 执行、程序指针、断点与符号 API。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import (
    embedded_resources,
    first_state,
    has_next_link,
    required_int,
    required_string,
    required_text,
    state_resources,
)
from omnicorectl.services.rapid import RapidAction

_IMPLICIT_MASTERSHIP = {"mastership": "implicit"}


@dataclass(frozen=True, slots=True)
class RapidExecutionState:
    state: str
    cycle: str
    hold_to_run: bool | None


@dataclass(frozen=True, slots=True)
class ProgramPointer:
    task: str
    kind: str
    module: str
    routine: str
    begin_row: int
    begin_column: int
    end_row: int
    end_column: int
    change_count: int | None
    execution_type: str


@dataclass(frozen=True, slots=True)
class Breakpoint:
    task: str
    module: str
    start_row: int
    start_column: int
    end_row: int
    end_column: int


@dataclass(frozen=True, slots=True)
class RapidSymbol:
    url: str
    name: str
    symbol_type: str
    data_type: str
    dimensions: str
    local: bool
    read_only: bool
    task_variable: bool
    type_url: str


@dataclass(frozen=True, slots=True)
class RapidSymbolData:
    url: str
    value: str
    declaration_begin_row: int | None
    declaration_begin_column: int | None
    declaration_end_row: int | None
    declaration_end_column: int | None
    initial_value_begin_row: int | None
    initial_value_begin_column: int | None
    initial_value_end_row: int | None
    initial_value_end_column: int | None


@dataclass(frozen=True, slots=True)
class MechanicalUnit:
    task: str
    name: str
    mode: str
    unit_type: str


@dataclass(frozen=True, slots=True)
class RobotTarget:
    task: str
    translation: tuple[str, ...]
    rotation: tuple[str, ...]
    configuration: tuple[str, ...]
    external_axes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JointTarget:
    task: str
    robot_axes: tuple[str, ...]
    external_axes: tuple[str, ...]


class RapidDebugService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def execution_state(self) -> RapidExecutionState:
        state = first_state(
            self._client.get_json("/rw/rapid/execution"),
            resource="RAPID execution state",
        )
        hold = _first_optional_string(state, ("holdtorun", "hdtrun"))
        return RapidExecutionState(
            state=required_text(
                state, "ctrlexecstate", resource="RAPID execution state"
            ),
            cycle=_first_required_string(
                state,
                ("rapidexeccycle", "cycle"),
                resource="RAPID execution state",
            ),
            hold_to_run=(
                None if not hold else _parse_bool(hold, resource="RAPID hold-to-run")
            ),
        )

    def start_execution(
        self,
        *,
        execution_mode: str = "continue",
        cycle: str = "asis",
        regain: str = "continue",
        condition: str = "none",
        stop_at_breakpoint: bool = True,
        all_tasks_by_task_panel: bool = False,
    ) -> RapidAction:
        execution_mode = execution_mode.lower()
        if execution_mode not in {
            "continue",
            "stepin",
            "stepover",
            "stepout",
            "stepback",
            "steplast",
            "stepmotion",
        }:
            raise ConfigurationError(
                f"unsupported RAPID execution mode: {execution_mode}"
            )
        if cycle not in {"forever", "asis", "once"}:
            raise ConfigurationError(f"unsupported RAPID execution cycle: {cycle}")
        self._client.post_form(
            "/rw/rapid/execution/start",
            {
                "regain": regain,
                "execmode": execution_mode,
                "cycle": cycle,
                "condition": condition,
                "stopatbp": "enabled" if stop_at_breakpoint else "disabled",
                "alltaskbytsp": _bool_text(all_tasks_by_task_panel),
            },
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction("*", "start", execution_mode)

    def stop_execution(
        self, *, stop_mode: str = "stop", all_tasks: bool = False
    ) -> RapidAction:
        if stop_mode not in {"cycle", "instr", "stop", "qstop"}:
            raise ConfigurationError(f"unsupported RAPID stop mode: {stop_mode}")
        self._client.post_form(
            "/rw/rapid/execution/stop",
            {"stopmode": stop_mode, "usetsp": "alltsk" if all_tasks else "normal"},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction("*", "stop", stop_mode)

    def reset_all_program_pointers(self) -> RapidAction:
        self._client.post_form(
            "/rw/rapid/execution/resetpp", params=_IMPLICIT_MASTERSHIP
        )
        return RapidAction("*", "reset-program-pointers", "main")

    def get_program_pointers(self, task: str) -> list[ProgramPointer]:
        task_path = _segment(task, "task")
        resources = _resources(
            self._client.get_json(f"/rw/rapid/tasks/{task_path}/pcp"),
            resource=f"RAPID program pointers {task}",
        )
        pointers = []
        for state in resources:
            if state.get("_type") != "pcp-info":
                continue
            # RW8 returns a nested error link when no PP/MP currently exists.
            # Treat that as an unavailable pointer rather than a malformed page.
            # RW8 在当前没有 PP/MP 时返回嵌套错误链接；这表示指针不可用，
            # 而不是响应格式损坏。
            if not isinstance(state.get("beginposition"), str):
                continue
            begin_row, begin_column = _position(
                required_text(state, "beginposition", resource="RAPID pointer")
            )
            end_row, end_column = _position(
                required_text(state, "endposition", resource="RAPID pointer")
            )
            raw_change_count = state.get("changecount")
            change_count = (
                required_int(state, "changecount", resource="RAPID pointer")
                if raw_change_count is not None
                else None
            )
            pointers.append(
                ProgramPointer(
                    task=task,
                    kind=_optional_string(state, "_title") or "unknown",
                    module=_first_optional_string(state, ("modulename", "modulemame")),
                    routine=_optional_string(state, "routinename"),
                    begin_row=begin_row,
                    begin_column=begin_column,
                    end_row=end_row,
                    end_column=end_column,
                    change_count=change_count,
                    execution_type=_optional_string(state, "executiontype"),
                )
            )
        return pointers

    def set_program_pointer_cursor(
        self, task: str, module: str, line: int, column: int
    ) -> RapidAction:
        _positive_position(line, column)
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/pcp/cursor",
            {"module": module, "line": str(line), "column": str(column)},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "set-program-pointer", f"{module}:{line}:{column}")

    def set_program_pointer_routine(
        self, task: str, module: str, routine: str, *, user_level: bool = False
    ) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/pcp/routine",
            {
                "module": module,
                "routine": routine,
                "userlevel": _bool_text(user_level),
            },
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "set-program-pointer", f"{module}/{routine}")

    def move_program_pointer(self, task: str, direction: str) -> RapidAction:
        if direction not in {"next", "previous"}:
            raise ConfigurationError(
                "program pointer direction must be next or previous"
            )
        task_path = _segment(task, "task")
        endpoint = "next-inst" if direction == "next" else "prev-inst"
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/pcp/{endpoint}",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, f"program-pointer-{direction}", task)

    def reset_program_pointer(self, task: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/pcp/reset",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "reset-program-pointer", "main")

    def list_breakpoints(self, task: str, *, page_size: int = 100) -> list[Breakpoint]:
        if page_size < 1 or page_size > 120:
            raise ConfigurationError("breakpoint page size must be between 1 and 120")
        task_path = _segment(task, "task")
        endpoint = f"/rw/rapid/tasks/{task_path}/program/breakpoints"
        start = 1
        breakpoints: list[Breakpoint] = []
        while True:
            payload = self._client.get_json(
                endpoint, params={"start": str(start), "limit": str(page_size)}
            )
            resources = _resources(payload, resource=f"RAPID breakpoints {task}")
            page = [
                _parse_breakpoint(task, state)
                for state in resources
                if state.get("_type") == "rap-program-breakpoint"
            ]
            breakpoints.extend(page)
            if not has_next_link(payload, resource=f"RAPID breakpoints {task}"):
                return breakpoints
            if not page:
                raise ProtocolError("RAPID breakpoints: next link did not advance")
            start += len(page)

    def set_breakpoint(
        self, task: str, module: str, row: int, column: int
    ) -> Breakpoint:
        _positive_position(row, column)
        task_path = _segment(task, "task")
        payload = self._client.post_form_optional_json(
            f"/rw/rapid/tasks/{task_path}/program/breakpoints",
            {"module": module, "row": str(row), "column": str(column)},
            params=_IMPLICIT_MASTERSHIP,
        )
        if payload is None:
            return Breakpoint(task, module, row, column, row, column)
        state = first_state(payload, resource="RAPID breakpoint")
        return Breakpoint(
            task,
            module,
            required_int(state, "start-row", resource="RAPID breakpoint"),
            required_int(state, "start-col", resource="RAPID breakpoint"),
            required_int(state, "end-row", resource="RAPID breakpoint"),
            required_int(state, "end-col", resource="RAPID breakpoint"),
        )

    def clear_breakpoint(
        self,
        task: str,
        *,
        module: str | None = None,
        row: int | None = None,
        column: int | None = None,
        all_breakpoints: bool = False,
    ) -> RapidAction:
        if not all_breakpoints and (module is None or row is None or column is None):
            raise ConfigurationError(
                "module, row, and column are required unless clearing all breakpoints"
            )
        task_path = _segment(task, "task")
        data = (
            {}
            if all_breakpoints
            else {"module": module or "", "row": str(row), "column": str(column)}
        )
        params = {**_IMPLICIT_MASTERSHIP, "all": _bool_text(all_breakpoints)}
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/breakpoints/remove",
            data,
            params=params,
        )
        target = "all" if all_breakpoints else f"{module}:{row}:{column}"
        return RapidAction(task, "clear-breakpoint", target)

    def search_symbols(
        self,
        *,
        block_url: str,
        regular_expression: str = ".*",
        symbol_type: str = "any",
        data_type: str | None = None,
        recursive: bool = True,
        variable_type: str = "any",
    ) -> list[RapidSymbol]:
        data = {
            "view": "block",
            "blockurl": block_url,
            "regexp": regular_expression,
            "symtyp": symbol_type,
            "recursive": _bool_text(recursive).upper(),
            "vartyp": variable_type,
            "skipshared": "FALSE",
            "onlyused": "FALSE",
            "posl": "0",
            "posc": "0",
            "stack": "0",
        }
        if data_type is not None:
            data["dattyp"] = data_type
        resources = _resources(
            self._client.post_json("/rw/rapid/symbols/search", data=data),
            resource="RAPID symbol search",
        )
        return [
            _parse_symbol(state)
            for state in resources
            if str(state.get("_type", "")).startswith(("rap-symbol", "rap-symprop"))
        ]

    def get_symbol_data(self, symbol_url: str) -> RapidSymbolData:
        normalized, endpoint = _symbol_endpoint(symbol_url)
        resources = _resources(
            self._client.get_json(endpoint), resource=f"RAPID symbol data {normalized}"
        )
        value_state = _find_resource(
            resources, "rap-data", resource=f"RAPID symbol data {normalized}"
        )
        declaration = _find_optional_resource(resources, "rap-data-decl-pos")
        initial = _find_optional_resource(resources, "rap-data-initval-pos")
        return RapidSymbolData(
            normalized,
            required_string(value_state, "value", resource="RAPID symbol data"),
            _optional_int(declaration, "begin-row"),
            _optional_int_any(declaration, ("begin-column", "begin-coloumn")),
            _optional_int(declaration, "end-row"),
            _optional_int_any(declaration, ("end-column", "end-coloumn")),
            _optional_int(initial, "begin-row"),
            _optional_int_any(initial, ("begin-column", "begin-coloumn")),
            _optional_int(initial, "end-row"),
            _optional_int_any(initial, ("end-column", "end-coloumn")),
        )

    def set_symbol_data(
        self,
        symbol_url: str,
        value: str,
        *,
        initial_value: bool = False,
        log_change: bool = False,
    ) -> RapidAction:
        normalized, endpoint = _symbol_endpoint(symbol_url)
        self._client.post_form(
            endpoint,
            {"value": value},
            params={
                **_IMPLICIT_MASTERSHIP,
                "initval": _bool_text(initial_value),
                "log": _bool_text(log_change),
            },
        )
        return RapidAction("*", "set-symbol-data", normalized)

    def validate_symbol_value(
        self, task: str, data_type: str, value: str
    ) -> RapidAction:
        self._client.post_form(
            "/rw/rapid/symbols/validate",
            {"task": task, "datatype": data_type, "value": value},
        )
        return RapidAction(task, "validate-symbol-value", data_type)

    def list_mechanical_units(self, task: str) -> list[MechanicalUnit]:
        task_path = _segment(task, "task")
        resources = _resources(
            self._client.get_json(f"/rw/rapid/tasks/{task_path}/motion/mechunits"),
            resource=f"RAPID mechanical units {task}",
        )
        return [
            MechanicalUnit(
                task,
                required_text(state, "name", resource="RAPID mechanical unit"),
                required_text(state, "mode", resource="RAPID mechanical unit"),
                required_text(state, "type", resource="RAPID mechanical unit"),
            )
            for state in resources
            if state.get("_type") == "rapid-mechunit"
        ]

    def get_robot_target(
        self, task: str, *, tool: str | None = None, work_object: str | None = None
    ) -> RobotTarget:
        task_path = _segment(task, "task")
        params = {}
        if tool is not None:
            params["tool"] = tool
        if work_object is not None:
            params["wobj"] = work_object
        state = first_state(
            self._client.get_json(
                f"/rw/rapid/tasks/{task_path}/motion/robtarget",
                params=params or None,
            ),
            resource=f"RAPID robtarget {task}",
        )
        return RobotTarget(
            task,
            _string_tuple(state, ("x", "y", "z"), resource="RAPID robtarget"),
            _string_tuple(state, ("q1", "q2", "q3", "q4"), resource="RAPID robtarget"),
            _string_tuple(
                state, ("cf1", "cf4", "cf6", "cfx"), resource="RAPID robtarget"
            ),
            _string_tuple(
                state,
                ("eax_a", "eax_b", "eax_c", "eax_d", "eax_e", "eax_f"),
                resource="RAPID robtarget",
            ),
        )

    def get_joint_target(self, task: str) -> JointTarget:
        task_path = _segment(task, "task")
        state = first_state(
            self._client.get_json(f"/rw/rapid/tasks/{task_path}/motion/jointtarget"),
            resource=f"RAPID jointtarget {task}",
        )
        return JointTarget(
            task,
            _string_tuple(
                state,
                ("rax_1", "rax_2", "rax_3", "rax_4", "rax_5", "rax_6"),
                resource="RAPID jointtarget",
            ),
            _string_tuple(
                state,
                ("eax_a", "eax_b", "eax_c", "eax_d", "eax_e", "eax_f"),
                resource="RAPID jointtarget",
            ),
        )


def _resources(payload: dict[str, Any], *, resource: str) -> list[dict[str, Any]]:
    if "state" in payload:
        return state_resources(payload, resource=resource)
    if "_embedded" in payload:
        return embedded_resources(payload, resource=resource)
    raise ProtocolError(f"{resource}: response has no resources")


def _segment(value: str, label: str) -> str:
    if not value.strip():
        raise ConfigurationError(f"RAPID {label} cannot be empty")
    return quote(value, safe="")


def _symbol_endpoint(symbol_url: str) -> tuple[str, str]:
    normalized = symbol_url.strip("/")
    if not normalized or any(
        segment in {".", ".."} for segment in normalized.split("/")
    ):
        raise ConfigurationError("invalid RAPID symbol URL")
    encoded = "/".join(quote(segment, safe="") for segment in normalized.split("/"))
    return normalized, f"/rw/rapid/symbol/{encoded}/data"


def _position(value: str) -> tuple[int, int]:
    row_text, separator, column_text = value.partition(",")
    if not separator:
        raise ProtocolError(f"invalid RAPID source position: {value!r}")
    try:
        return int(row_text.strip()), int(column_text.strip())
    except ValueError as exc:
        raise ProtocolError(f"invalid RAPID source position: {value!r}") from exc


def _positive_position(row: int, column: int) -> None:
    if row < 1 or column < 0:
        raise ConfigurationError("RAPID row must be positive and column non-negative")


def _optional_string(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    return value if isinstance(value, str) else ""


def _first_optional_string(state: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = state.get(key)
        if isinstance(value, str):
            return value
    return ""


def _first_required_string(
    state: dict[str, Any], keys: tuple[str, ...], *, resource: str
) -> str:
    value = _first_optional_string(state, keys)
    if not value:
        raise ProtocolError(f"{resource}: missing one of {keys!r}")
    return value


def _parse_bool(value: str, *, resource: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "on", "1", "yes"}:
        return True
    if normalized in {"false", "off", "0", "no", ""}:
        return False
    raise ProtocolError(f"{resource}: invalid boolean {value!r}")


def _parse_breakpoint(task: str, state: dict[str, Any]) -> Breakpoint:
    return Breakpoint(
        task,
        required_text(state, "module-name", resource="RAPID breakpoint"),
        required_int(state, "start-row", resource="RAPID breakpoint"),
        required_int(state, "start-col", resource="RAPID breakpoint"),
        required_int(state, "end-row", resource="RAPID breakpoint"),
        required_int(state, "end-col", resource="RAPID breakpoint"),
    )


def _parse_symbol(state: dict[str, Any]) -> RapidSymbol:
    local = _optional_string(state, "local") or "false"
    read_only = _optional_string(state, "rdonly") or "false"
    task_variable = (
        _optional_string(state, "taskvar")
        or _optional_string(state, "taskpers")
        or "false"
    )
    return RapidSymbol(
        url=required_text(state, "symburl", resource="RAPID symbol"),
        name=required_text(state, "name", resource="RAPID symbol"),
        symbol_type=required_text(state, "symtyp", resource="RAPID symbol"),
        data_type=_optional_string(state, "dattyp"),
        dimensions=_optional_string(state, "dim"),
        local=_parse_bool(local, resource="RAPID symbol local"),
        read_only=_parse_bool(read_only, resource="RAPID symbol read-only"),
        task_variable=_parse_bool(task_variable, resource="RAPID symbol task variable"),
        type_url=_optional_string(state, "typurl"),
    )


def _find_resource(
    resources: list[dict[str, Any]], resource_type: str, *, resource: str
) -> dict[str, Any]:
    match = _find_optional_resource(resources, resource_type)
    if match is None:
        raise ProtocolError(f"{resource}: response has no {resource_type} resource")
    return match


def _find_optional_resource(
    resources: list[dict[str, Any]], resource_type: str
) -> dict[str, Any] | None:
    for state in resources:
        if state.get("_type") == resource_type:
            return state
    return None


def _optional_int(state: dict[str, Any] | None, key: str) -> int | None:
    if state is None or key not in state:
        return None
    return required_int(state, key, resource="RAPID symbol position")


def _optional_int_any(
    state: dict[str, Any] | None, keys: tuple[str, ...]
) -> int | None:
    if state is None:
        return None
    for key in keys:
        if key in state:
            return required_int(state, key, resource="RAPID symbol position")
    return None


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _string_tuple(
    state: dict[str, Any], keys: tuple[str, ...], *, resource: str
) -> tuple[str, ...]:
    return tuple(required_string(state, key, resource=resource) for key in keys)
