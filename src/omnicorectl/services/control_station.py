"""RobotWare 8 Control Station and write-access resources.

RobotWare 8 控制站与写权限资源。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from omnicorectl.errors import ConfigurationError, OmnicoreError, ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_bool, required_text


@dataclass(frozen=True, slots=True)
class WriteAccessStatus:
    held: bool
    external_control_enabled: bool
    holder_id: str
    holder_name: str


@dataclass(frozen=True, slots=True)
class RemoteControlStation:
    name: str
    station_id: str
    pin: str
    release_when_lost: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Control Station name cannot be empty")
        try:
            UUID(self.station_id)
        except ValueError as exc:
            raise ConfigurationError("Control Station ID must be a UUID") from exc
        if not self.pin.isdigit():
            raise ConfigurationError("Control Station PIN must contain only digits")

    @property
    def wire_id(self) -> str:
        """Return ABB's required braced GUID representation.

        返回 ABB 要求的带花括号 GUID 表示形式。
        """

        return f"{{{UUID(self.station_id)}}}"


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

    def register_remote(self, station: RemoteControlStation) -> None:
        self._client.post_form(
            "/rw/controlstation/register/remote",
            {
                "control-station-name": station.name,
                "control-station-id": station.wire_id,
                "pincode": station.pin,
                "release-write-access-when-lost": (
                    "true" if station.release_when_lost else "false"
                ),
            },
        )

    def request_write_access(self) -> None:
        self._client.post_form("/rw/controlstation/writeaccess/request")

    def release_write_access(self) -> None:
        self._client.post_form("/rw/controlstation/writeaccess/release")

    @contextmanager
    def write_access(
        self,
        station: RemoteControlStation,
        *,
        best_effort_release: bool = False,
    ) -> Iterator[WriteAccessStatus]:
        """Hold write access for one bounded operation and always release it.

        仅在一个有界操作期间持有写权限，并始终释放该权限。
        """

        self.register_remote(station)
        acquired = False
        try:
            self.request_write_access()
            acquired = True
            status = self.status()
            if not status.external_control_enabled:
                raise ProtocolError("external control is not enabled on the controller")
            holder_id = status.holder_id.strip("{}").lower()
            if not status.held or holder_id != str(UUID(station.station_id)).lower():
                raise ProtocolError(
                    "write access request completed but this Control Station is not the holder"
                )
            yield status
        finally:
            if acquired:
                try:
                    self.release_write_access()
                except OmnicoreError:
                    if not best_effort_release:
                        raise
