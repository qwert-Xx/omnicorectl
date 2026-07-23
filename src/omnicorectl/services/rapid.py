"""RAPID source, program, execution, and debugging resources.

RAPID 源码、程序、执行与调试资源。
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
    required_bool,
    required_int,
    required_string,
    required_text,
    state_resources,
)

_IMPLICIT_MASTERSHIP = {"mastership": "implicit"}


@dataclass(frozen=True, slots=True)
class RapidTask:
    name: str
    task_type: str
    task_state: str
    execution_state: str
    active: bool
    motion_task: bool


@dataclass(frozen=True, slots=True)
class RapidModule:
    task: str
    name: str
    module_type: str


@dataclass(frozen=True, slots=True)
class ModuleSource:
    task: str
    module: str
    change_count: int
    reported_length: int
    source: str


@dataclass(frozen=True, slots=True)
class ModuleAttributes:
    task: str
    module: str
    filename: str
    attributes: tuple[str, ...]

    @property
    def read_only(self) -> bool:
        return "readonly" in {value.lower() for value in self.attributes}


@dataclass(frozen=True, slots=True)
class ModuleTextRange:
    task: str
    module: str
    start_row: int
    start_column: int
    end_row: int
    end_column: int
    text: str


@dataclass(frozen=True, slots=True)
class ModuleExtension:
    task: str
    module: str
    lines: int
    maximum_columns: int
    change_count: int


@dataclass(frozen=True, slots=True)
class TextPosition:
    task: str
    module: str
    row: int
    column: int


@dataclass(frozen=True, slots=True)
class ModifiablePositionRange:
    task: str
    module: str
    count: int
    start_row: int
    start_column: int
    end_row: int
    end_column: int


@dataclass(frozen=True, slots=True)
class ModuleChange:
    task: str
    module: str
    changed: bool
    renamed: bool
    new_module_name: str
    change_count_before: int
    change_count_after: int


@dataclass(frozen=True, slots=True)
class RapidAction:
    task: str
    action: str
    target: str


@dataclass(frozen=True, slots=True)
class ModuleLoadResult:
    task: str
    module_path: str
    module: str
    replaced: bool


@dataclass(frozen=True, slots=True)
class BuildError:
    task: str
    module: str
    row: int
    column: int
    message: str
    error_number: str


@dataclass(frozen=True, slots=True)
class RapidProgram:
    task: str
    name: str
    entry_point: str


class RapidService:
    """Typed facade over the RobotWare 8 RAPID RWS 2.0 service.

    RobotWare 8 RAPID RWS 2.0 服务的类型化门面。
    """

    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def list_tasks(self) -> list[RapidTask]:
        resources = embedded_resources(
            self._client.get_json("/rw/rapid/tasks"), resource="RAPID tasks"
        )
        tasks = []
        for item in resources:
            if item.get("_type") != "rap-task-li":
                continue
            tasks.append(
                RapidTask(
                    name=required_text(item, "name", resource="RAPID task"),
                    task_type=required_text(item, "type", resource="RAPID task"),
                    task_state=required_text(item, "taskstate", resource="RAPID task"),
                    execution_state=required_text(
                        item, "excstate", resource="RAPID task"
                    ),
                    active=required_bool(item, "active", resource="RAPID task"),
                    motion_task=required_bool(
                        item, "motiontask", resource="RAPID task"
                    ),
                )
            )
        return tasks

    def list_modules(self, task: str) -> list[RapidModule]:
        task_path = _segment(task, "task")
        resources = state_resources(
            self._client.get_json(f"/rw/rapid/tasks/{task_path}/modules"),
            resource=f"RAPID modules for {task}",
        )
        modules = []
        for item in resources:
            if item.get("_type") != "rap-module-info-li":
                continue
            modules.append(
                RapidModule(
                    task=task,
                    name=required_text(item, "name", resource="RAPID module"),
                    module_type=required_text(item, "type", resource="RAPID module"),
                )
            )
        return modules

    def get_module_source(self, task: str, module: str) -> ModuleSource:
        endpoint = _module_endpoint(task, module, "/text")
        state = first_state(
            self._client.get_json(endpoint),
            resource=f"RAPID source {task}/{module}",
        )
        return ModuleSource(
            task=task,
            module=module,
            change_count=required_int(
                state, "change-count", resource="RAPID module source"
            ),
            reported_length=required_int(
                state, "module-length", resource="RAPID module source"
            ),
            source=required_text(state, "module-text", resource="RAPID module source"),
        )

    def get_module_attributes(self, task: str, module: str) -> ModuleAttributes:
        endpoint = _module_endpoint(task, module)
        resources = state_resources(
            self._client.get_json(endpoint),
            resource=f"RAPID module attributes {task}/{module}",
        )
        state = _find_resource(
            resources,
            "rap-module",
            resource=f"RAPID module attributes {task}/{module}",
        )
        raw_attributes = required_string(
            state, "attribute", resource="RAPID module attributes"
        )
        return ModuleAttributes(
            task=task,
            module=required_text(state, "modname", resource="RAPID module attributes"),
            filename=required_string(
                state, "filename", resource="RAPID module attributes"
            ),
            attributes=tuple(
                value.strip() for value in raw_attributes.split(",") if value.strip()
            ),
        )

    def get_text_range(
        self,
        task: str,
        module: str,
        *,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
    ) -> ModuleTextRange:
        _validate_source_range(
            start_row,
            start_column,
            end_row,
            end_column,
            allow_end_of_line=True,
        )
        endpoint = _module_endpoint(task, module, "/text/range")
        state = first_state(
            self._client.get_json(
                endpoint,
                params={
                    "startrow": str(start_row),
                    "startcol": str(start_column),
                    "endrow": str(end_row),
                    "endcol": str(end_column),
                },
            ),
            resource=f"RAPID text range {task}/{module}",
        )
        text = _first_string(
            state, ("text", "module-text"), resource="RAPID text range"
        )
        return ModuleTextRange(
            task,
            module,
            start_row,
            start_column,
            end_row,
            end_column,
            text,
        )

    def get_change_count(self, task: str, module: str) -> int:
        state = first_state(
            self._client.get_json(_module_endpoint(task, module, "/changecount")),
            resource=f"RAPID change count {task}/{module}",
        )
        return required_int(state, "count", resource="RAPID module change count")

    def get_module_extension(self, task: str, module: str) -> ModuleExtension:
        state = first_state(
            self._client.get_json(_module_endpoint(task, module, "/module-extension")),
            resource=f"RAPID module extension {task}/{module}",
        )
        return ModuleExtension(
            task,
            module,
            required_int(state, "num-of-lines", resource="RAPID module extension"),
            required_int(state, "max-num-of-col", resource="RAPID module extension"),
            required_int(state, "count", resource="RAPID module extension"),
        )

    def search_text(
        self,
        task: str,
        module: str,
        text: str,
        *,
        start_row: int = 1,
        start_column: int = 1,
    ) -> TextPosition | None:
        if not text:
            raise ConfigurationError("RAPID search text cannot be empty")
        _validate_source_range(start_row, start_column, start_row, start_column)
        state = first_state(
            self._client.get_json(
                _module_endpoint(task, module, "/text/search"),
                params={
                    "startrow": str(start_row),
                    "startcol": str(start_column),
                    "text": text,
                },
            ),
            resource=f"RAPID text search {task}/{module}",
        )
        row = required_int(state, "Row", resource="RAPID text search")
        column = required_int(state, "Column", resource="RAPID text search")
        return (
            None
            if row == 0 and column == 0
            else TextPosition(task, module, row, column)
        )

    def sync_persistent_data(self, task: str, module: str) -> RapidAction:
        self._client.post_form(
            _module_endpoint(task, module, "/sync-pers"),
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "sync-persistent-data", module)

    def persistent_data_is_synchronized(self, task: str, module: str) -> bool:
        state = first_state(
            self._client.get_json(_module_endpoint(task, module, "/sync-pers")),
            resource=f"RAPID persistent-data status {task}/{module}",
        )
        value = required_text(
            state, "syncperstatus", resource="RAPID persistent-data status"
        ).strip()
        if value in {"1", "true", "TRUE"}:
            return True
        if value in {"0", "false", "FALSE"}:
            return False
        raise ProtocolError(f"invalid RAPID SyncPers status: {value!r}")

    def get_modifiable_positions(
        self,
        task: str,
        module: str,
        *,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
    ) -> ModifiablePositionRange:
        _validate_source_range(start_row, start_column, end_row, end_column)
        state = first_state(
            self._client.get_json(
                _module_endpoint(task, module, "/mod-possible"),
                params={
                    "startrow": str(start_row),
                    "startcol": str(start_column),
                    "endrow": str(end_row),
                    "endcol": str(end_column),
                },
            ),
            resource=f"RAPID modifiable positions {task}/{module}",
        )
        return ModifiablePositionRange(
            task,
            module,
            required_int(state, "no_lines_modifiable", resource="modifiable positions"),
            required_int(state, "start_row", resource="modifiable positions"),
            required_int(state, "start_col", resource="modifiable positions"),
            required_int(state, "end_row", resource="modifiable positions"),
            required_int(state, "end_col", resource="modifiable positions"),
        )

    def modify_position(
        self,
        task: str,
        module: str,
        *,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
        check_limits: bool = True,
        check_deactivated_axes: bool = True,
        allow_deactivated_axes: bool = False,
    ) -> RapidAction:
        _validate_source_range(start_row, start_column, end_row, end_column)
        self._client.post_form(
            _module_endpoint(task, module, "/modify-position"),
            {
                "startrow": str(start_row),
                "startcol": str(start_column),
                "endrow": str(end_row),
                "endcol": str(end_column),
                "checklimit": _bool_text(check_limits),
                "checkdeactaxes": _bool_text(check_deactivated_axes),
                "allowdeact": _bool_text(allow_deactivated_axes),
            },
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(
            task,
            "modify-position",
            f"{module}:{start_row}:{start_column}-{end_row}:{end_column}",
        )

    def set_module_text(
        self,
        task: str,
        module: str,
        text: str,
        *,
        expected_change_count: int | None = None,
    ) -> ModuleChange:
        if not text:
            raise ConfigurationError("RAPID module source cannot be empty")
        before = self.get_change_count(task, module)
        _check_change_count(expected_change_count, before, task, module)
        payload = self._client.post_form_optional_json(
            _module_endpoint(task, module, "/text"),
            {"text": text},
            params=_IMPLICIT_MASTERSHIP,
        )
        renamed, new_name, returned_count = _parse_module_change(payload)
        after = returned_count
        if after is None:
            after = self.get_change_count(task, new_name or module)
        return ModuleChange(
            task=task,
            module=module,
            changed=after != before,
            renamed=renamed,
            new_module_name=new_name,
            change_count_before=before,
            change_count_after=after,
        )

    def set_text_range(
        self,
        task: str,
        module: str,
        *,
        replace_mode: str,
        start_row: int,
        start_column: int,
        end_row: int,
        end_column: int,
        text: str,
        query_mode: str = "Force",
        expected_change_count: int | None = None,
    ) -> ModuleChange:
        replace = replace_mode.capitalize()
        query = query_mode.capitalize()
        if replace not in {"Before", "After", "Replace"}:
            raise ConfigurationError("replace mode must be Before, After, or Replace")
        if query not in {"Force", "Try"}:
            raise ConfigurationError("query mode must be Force or Try")
        _validate_source_range(start_row, start_column, end_row, end_column)
        before = self.get_change_count(task, module)
        _check_change_count(expected_change_count, before, task, module)
        payload = self._client.post_form_optional_json(
            _module_endpoint(task, module, "/text/range"),
            {
                "replace-mode": replace,
                "query-mode": query,
                "startrow": str(start_row),
                "startcol": str(start_column),
                "endrow": str(end_row),
                "endcol": str(end_column),
                "text": text,
            },
            params=_IMPLICIT_MASTERSHIP,
        )
        renamed, new_name, returned_count = _parse_module_change(payload)
        after = returned_count
        if after is None:
            after = self.get_change_count(task, new_name or module)
        return ModuleChange(
            task,
            module,
            after != before,
            renamed,
            new_name,
            before,
            after,
        )

    def save_module(
        self, task: str, module: str, *, path: str, name: str | None = None
    ) -> RapidAction:
        if not path.strip():
            raise ConfigurationError("RAPID module save path cannot be empty")
        self._client.post_form(
            _module_endpoint(task, module, "/save"),
            {"name": name or module, "path": path},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "save-module", f"{path.rstrip('/')}/{name or module}")

    def load_module(
        self, task: str, module_path: str, *, replace: bool = False
    ) -> ModuleLoadResult:
        if not module_path.strip():
            raise ConfigurationError("RAPID module path cannot be empty")
        task_path = _segment(task, "task")
        payload = self._client.post_form_optional_json(
            f"/rw/rapid/tasks/{task_path}/loadmod",
            {"modulepath": module_path, "replace": _bool_text(replace)},
            params=_IMPLICIT_MASTERSHIP,
        )
        loaded_name = ""
        if payload is not None:
            resources = _resources(payload, resource="loaded RAPID module")
            for item in resources:
                if item.get("_type") in {"rap-task-module-li", "rap-module-info-li"}:
                    loaded_name = _optional_string(item, "name")
                    break
        return ModuleLoadResult(task, module_path, loaded_name, replace)

    def unload_module(self, task: str, module: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/unloadmod",
            {"module": module},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "unload-module", module)

    def build_task(self, task: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/build",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "build", task)

    def get_build_errors(self, task: str, *, page_size: int = 100) -> list[BuildError]:
        if page_size < 1 or page_size > 120:
            raise ConfigurationError("build error page size must be between 1 and 120")
        task_path = _segment(task, "task")
        endpoint = f"/rw/rapid/tasks/{task_path}/program/builderror"
        start = 1
        errors: list[BuildError] = []
        while True:
            payload = self._client.get_json(
                endpoint, params={"start": str(start), "limit": str(page_size)}
            )
            resources = _resources(payload, resource=f"RAPID build errors for {task}")
            page = [
                _parse_build_error(task, item)
                for item in resources
                if str(item.get("_type", "")).startswith("rap-builderr")
            ]
            errors.extend(page)
            if not has_next_link(payload, resource=f"RAPID build errors for {task}"):
                return errors
            if not page:
                raise ProtocolError("RAPID build errors: next link did not advance")
            start += len(page)

    def get_program(self, task: str) -> RapidProgram:
        task_path = _segment(task, "task")
        resources = _resources(
            self._client.get_json(f"/rw/rapid/tasks/{task_path}/program"),
            resource=f"RAPID program {task}",
        )
        state = _find_resource(
            resources, "rap-program", resource=f"RAPID program {task}"
        )
        return RapidProgram(
            task,
            required_string(state, "name", resource="RAPID program"),
            required_string(state, "entrypoint", resource="RAPID program"),
        )

    def load_program(
        self, task: str, program_path: str, *, replace: bool = False
    ) -> RapidAction:
        if not program_path.strip():
            raise ConfigurationError("RAPID program path cannot be empty")
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/load",
            {"progpath": program_path, "replace": _bool_text(replace)},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "load-program", program_path)

    def unload_program(self, task: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/unload",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "unload-program", task)

    def save_program(self, task: str, path: str) -> RapidAction:
        if not path.strip():
            raise ConfigurationError("RAPID program save path cannot be empty")
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/save",
            {"path": path},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "save-program", path)

    def set_program_name(self, task: str, name: str) -> RapidAction:
        if not name.strip():
            raise ConfigurationError("RAPID program name cannot be empty")
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/name",
            {"name": name},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "set-program-name", name)

    def set_entry_point(self, task: str, routine: str) -> RapidAction:
        if not routine.strip():
            raise ConfigurationError("RAPID entry point cannot be empty")
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/program/entrypoint",
            {"routine": routine},
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "set-entry-point", routine)

    def activate_task(self, task: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/activate",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "activate-task", task)

    def deactivate_task(self, task: str) -> RapidAction:
        task_path = _segment(task, "task")
        self._client.post_form(
            f"/rw/rapid/tasks/{task_path}/deactivate",
            params=_IMPLICIT_MASTERSHIP,
        )
        return RapidAction(task, "deactivate-task", task)


def _segment(value: str, label: str) -> str:
    if not value.strip():
        raise ConfigurationError(f"RAPID {label} cannot be empty")
    return quote(value, safe="")


def _module_endpoint(task: str, module: str, suffix: str = "") -> str:
    return (
        f"/rw/rapid/tasks/{_segment(task, 'task')}/modules/"
        f"{_segment(module, 'module')}{suffix}"
    )


def _resources(payload: dict[str, Any], *, resource: str) -> list[dict[str, Any]]:
    if "state" in payload:
        return state_resources(payload, resource=resource)
    if "_embedded" in payload:
        return embedded_resources(payload, resource=resource)
    raise ProtocolError(f"{resource}: response has no resources")


def _find_resource(
    resources: list[dict[str, Any]], resource_type: str, *, resource: str
) -> dict[str, Any]:
    for item in resources:
        if item.get("_type") == resource_type:
            return item
    raise ProtocolError(f"{resource}: response has no {resource_type} resource")


def _optional_string(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    return value if isinstance(value, str) else ""


def _first_string(
    state: dict[str, Any], keys: tuple[str, ...], *, resource: str
) -> str:
    for key in keys:
        value = state.get(key)
        if isinstance(value, str):
            return value
    raise ProtocolError(f"{resource}: missing one of {keys!r}")


def _parse_module_change(
    payload: dict[str, Any] | None,
) -> tuple[bool, str, int | None]:
    if payload is None:
        return False, "", None
    state = first_state(payload, resource="RAPID module change")
    renamed_text = _optional_string(state, "module-changed-name").strip().lower()
    renamed = renamed_text in {"true", "1", "yes", "on"}
    new_name = _optional_string(state, "new-modnam")
    raw_count = state.get("change-count")
    if raw_count is None:
        return renamed, new_name, None
    return (
        renamed,
        new_name,
        required_int(state, "change-count", resource="RAPID module change"),
    )


def _check_change_count(
    expected: int | None, actual: int, task: str, module: str
) -> None:
    if expected is not None and expected != actual:
        raise ConfigurationError(
            f"RAPID module changed concurrently: {task}/{module} expected "
            f"change count {expected}, current value is {actual}"
        )


def _validate_source_range(
    start_row: int,
    start_column: int,
    end_row: int,
    end_column: int,
    *,
    allow_end_of_line: bool = False,
) -> None:
    values = (start_row, start_column, end_row)
    valid_end_column = end_column > 0 or (allow_end_of_line and end_column == -1)
    if any(value < 1 for value in values) or not valid_end_column:
        suffix = "; end column may be -1 for reads" if allow_end_of_line else ""
        raise ConfigurationError(
            f"RAPID source rows and columns must be positive{suffix}"
        )
    if (end_row, end_column if end_column != -1 else 2**31) < (
        start_row,
        start_column,
    ):
        raise ConfigurationError("RAPID source range ends before it starts")


def _parse_build_error(task: str, state: dict[str, Any]) -> BuildError:
    return BuildError(
        task=task,
        module=_first_string(
            state, ("ModuleName", "module-name"), resource="RAPID build error"
        ),
        row=required_int(state, "row", resource="RAPID build error"),
        column=required_int(state, "column", resource="RAPID build error"),
        message=required_text(state, "error", resource="RAPID build error"),
        error_number=_optional_string(state, "error-num"),
    )


def _bool_text(value: bool) -> str:
    return "true" if value else "false"
