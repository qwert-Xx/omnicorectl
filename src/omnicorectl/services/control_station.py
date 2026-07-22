"""RobotWare 8 Control Station and write-access resources."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_bool, required_text


@dataclass(frozen=True, slots=True)
class WriteAccessStatus:
    held: bool
    external_control_enabled: bool
    holder_id: str
    holder_name: str


class ControlStationService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def status(self) -> WriteAccessStatus:
        state = first_state(
            self._client.get_json("/rw/controlstation/writeaccess/status"),
            resource="Control Station write access",
        )
        return WriteAccessStatus(
            held=required_bool(
                state,
                "control-station-write-access-held",
                resource="Control Station write access",
            ),
            external_control_enabled=required_bool(
                state,
                "control-station-external-control-enabled",
                resource="Control Station write access",
            ),
            holder_id=required_text(
                state,
                "held-by-control-station-Id",
                resource="Control Station write access",
            ),
            holder_name=required_text(
                state,
                "held-by-control-station-name",
                resource="Control Station write access",
            ),
        )
