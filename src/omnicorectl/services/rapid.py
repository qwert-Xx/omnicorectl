"""Read-only RAPID resources."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import embedded_resources, required_bool, required_text


@dataclass(frozen=True, slots=True)
class RapidTask:
    name: str
    task_type: str
    task_state: str
    execution_state: str
    active: bool
    motion_task: bool


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
