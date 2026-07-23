"""Controller backup workflows. / 控制器备份工作流。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_text
from omnicorectl.services.files import FileService


@dataclass(frozen=True, slots=True)
class BackupStatus:
    state: str


@dataclass(frozen=True, slots=True)
class BackupResult:
    destination: str
    artifact_path: str
    archive: bool
    progress_uri: str
    state: str
    code: str
    resource_path: str


class BackupService:
    def __init__(
        self,
        client: RwsClient,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._clock = clock
        self._sleep = sleep

    def status(self) -> BackupStatus:
        state = first_state(
            self._client.get_json("/ctrl/backup/state"), resource="backup state"
        )
        return BackupStatus(
            state=required_text(state, "backup-state", resource="backup state")
        )

    def create(
        self,
        destination: str,
        *,
        archive: bool = True,
        overwrite: bool = False,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
    ) -> BackupResult:
        normalized = _backup_destination(destination)
        backup_status = self.status()
        if backup_status.state.lower() != "backup ready":
            raise ProtocolError(
                f"controller backup service is not ready: {backup_status.state}"
            )
        artifact_path = f"{normalized}.tar" if archive else normalized
        artifact = PurePosixPath(artifact_path)
        if not overwrite and any(
            entry.name == artifact.name
            for entry in FileService(self._client).list_directory(str(artifact.parent))
        ):
            raise ConfigurationError(
                f"backup destination already exists: {artifact_path}"
            )
        progress_uri = self._client.post_form_location(
            "/ctrl/backup/create",
            {
                "backup": f"/fileservice{normalized}",
                "archive": "TRUE" if archive else "FALSE",
            },
        )
        deadline = self._clock() + timeout
        while True:
            progress = _parse_progress(self._client.get_json(progress_uri))
            if progress.state.lower() != "pending":
                break
            if self._clock() >= deadline:
                raise ProtocolError(
                    f"backup did not complete within {timeout:g} seconds; "
                    f"progress remains at {progress_uri}"
                )
            self._sleep(min(poll_interval, max(0.0, deadline - self._clock())))

        if progress.state.lower() != "ready" or progress.code not in {
            "294912",
            "294913",
        }:
            raise ProtocolError(
                f"backup failed: state={progress.state!r}, code={progress.code!r}"
            )
        return BackupResult(
            destination=normalized,
            artifact_path=artifact_path,
            archive=archive,
            progress_uri=progress_uri,
            state=progress.state,
            code=progress.code,
            resource_path=progress.resource_path,
        )


@dataclass(frozen=True, slots=True)
class _Progress:
    state: str
    code: str
    resource_path: str


def _backup_destination(path: str) -> str:
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if not segments:
        raise ConfigurationError("a backup destination is required")
    if any(segment in {".", ".."} for segment in segments):
        raise ConfigurationError("backup destination cannot contain '.' or '..'")
    if segments[0].lower() == "$home":
        raise ConfigurationError("ABB does not allow backups under $HOME")
    return "/" + "/".join(segments)


def _parse_progress(payload: dict[str, object]) -> _Progress:
    states = payload.get("state")
    if not isinstance(states, list) or not states or not isinstance(states[0], dict):
        raise ProtocolError("backup progress: expected a non-empty state list")
    item = states[0]
    state = required_text(item, "state", resource="backup progress")
    code = required_text(item, "code", resource="backup progress")
    resource_path = ""
    links = item.get("_links")
    if isinstance(links, dict):
        resource = links.get("resource")
        if isinstance(resource, dict):
            href = resource.get("href")
            if isinstance(href, str):
                resource_path = href
    return _Progress(state=state, code=code, resource_path=resource_path)
