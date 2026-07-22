"""Read-only RAPID resources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import (
    embedded_resources,
    required_bool,
    required_int,
    required_text,
    first_state,
    state_resources,
)


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


class RapidService:
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
                    task_state=required_text(
                        item, "taskstate", resource="RAPID task"
                    ),
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
        task_path = quote(task, safe="")
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
                    module_type=required_text(
                        item, "type", resource="RAPID module"
                    ),
                )
            )
        return modules

    def get_module_source(self, task: str, module: str) -> ModuleSource:
        task_path = quote(task, safe="")
        module_path = quote(module, safe="")
        state = first_state(
            self._client.get_json(
                f"/rw/rapid/tasks/{task_path}/modules/{module_path}/text"
            ),
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
            source=required_text(
                state, "module-text", resource="RAPID module source"
            ),
        )
