"""Controller backup workflows."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_text


@dataclass(frozen=True, slots=True)
class BackupStatus:
    state: str


class BackupService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def status(self) -> BackupStatus:
        state = first_state(
            self._client.get_json("/ctrl/backup/state"), resource="backup state"
        )
        return BackupStatus(
            state=required_text(state, "backup-state", resource="backup state")
        )
