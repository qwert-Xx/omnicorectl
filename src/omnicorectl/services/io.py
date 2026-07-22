"""Read-only I/O system resources."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.errors import ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import embedded_resources, required_text


@dataclass(frozen=True, slots=True)
class IoNetwork:
    name: str
    physical_state: str
    logical_state: str


@dataclass(frozen=True, slots=True)
class IoDevice:
    network: str
    name: str
    physical_state: str
    logical_state: str
    address: str


class IoService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def list_networks(self) -> list[IoNetwork]:
        resources = embedded_resources(
            self._client.get_json("/rw/iosystem/networks"),
            resource="I/O networks",
        )
        networks = []
        for item in resources:
            if item.get("_type") != "ios-network-li":
                continue
            networks.append(
                IoNetwork(
                    name=required_text(item, "name", resource="I/O network"),
                    physical_state=required_text(
                        item, "pstate", resource="I/O network"
                    ),
                    logical_state=required_text(
                        item, "lstate", resource="I/O network"
                    ),
                )
            )
        return networks

    def list_devices(self, network: str) -> list[IoDevice]:
        resources = embedded_resources(
            self._client.get_json(
                "/rw/iosystem/devices", params={"network": network}
            ),
            resource=f"I/O devices on {network}",
        )
        devices = []
        for item in resources:
            if item.get("_type") != "ios-device-li":
                continue
            address = item.get("address")
            if not isinstance(address, str):
                raise ProtocolError("I/O device: missing text field 'address'")
            devices.append(
                IoDevice(
                    network=network,
                    name=required_text(item, "name", resource="I/O device"),
                    physical_state=required_text(
                        item, "pstate", resource="I/O device"
                    ),
                    logical_state=required_text(
                        item, "lstate", resource="I/O device"
                    ),
                    address=address,
                )
            )
        return devices
