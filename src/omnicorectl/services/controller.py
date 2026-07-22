"""Read-only controller information workflows."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_text


@dataclass(frozen=True, slots=True)
class ControllerStatus:
    name: str
    controller_id: str
    controller_type: str
    mac_address: str
    operation_mode: str
    controller_state: str
    rapid_execution: str
    execution_cycle: str


class ControllerService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def status(self) -> ControllerStatus:
        identity = first_state(
            self._client.get_json("/ctrl/identity"), resource="controller identity"
        )
        operation_mode = first_state(
            self._client.get_json("/rw/panel/opmode"), resource="operation mode"
        )
        controller_state = first_state(
            self._client.get_json("/rw/panel/ctrl-state"),
            resource="controller state",
        )
        execution = first_state(
            self._client.get_json("/rw/rapid/execution"),
            resource="RAPID execution",
        )

        return ControllerStatus(
            name=required_text(identity, "ctrl-name", resource="controller identity"),
            controller_id=required_text(
                identity, "ctrl-id", resource="controller identity"
            ),
            controller_type=required_text(
                identity, "ctrl-type", resource="controller identity"
            ),
            mac_address=required_text(
                identity, "ctrl-mac", resource="controller identity"
            ),
            operation_mode=required_text(
                operation_mode, "opmode", resource="operation mode"
            ),
            controller_state=required_text(
                controller_state, "ctrlstate", resource="controller state"
            ),
            rapid_execution=required_text(
                execution, "ctrlexecstate", resource="RAPID execution"
            ),
            execution_cycle=required_text(
                execution, "cycle", resource="RAPID execution"
            ),
        )

