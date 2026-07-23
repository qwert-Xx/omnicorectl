"""Read-only I/O system resources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from omnicorectl.errors import ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import (
    embedded_resources,
    has_next_link,
    required_string,
    required_text,
)


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


@dataclass(frozen=True, slots=True)
class IoSignal:
    network: str | None
    device: str | None
    name: str
    signal_type: str
    category: str
    value: str
    state: str


@dataclass(frozen=True, slots=True)
class IoSignalDetails:
    network: str
    device: str
    name: str
    signal_type: str
    category: str
    logical_value: str
    logical_state: str
    physical_value: str
    physical_state: str
    quality: str
    access_level: str
    write_access: str
    safety_level: str


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
                    logical_state=required_text(item, "lstate", resource="I/O network"),
                )
            )
        return networks

    def list_devices(self, network: str) -> list[IoDevice]:
        resources = embedded_resources(
            self._client.get_json("/rw/iosystem/devices", params={"network": network}),
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
                    physical_state=required_text(item, "pstate", resource="I/O device"),
                    logical_state=required_text(item, "lstate", resource="I/O device"),
                    address=address,
                )
            )
        return devices

    def list_signals(
        self,
        *,
        network: str | None = None,
        device: str | None = None,
        signal_type: str | None = None,
        name: str | None = None,
        page_size: int = 200,
    ) -> list[IoSignal]:
        filters = {
            key: value
            for key, value in {
                "network": network,
                "device": device,
                "type": signal_type,
                "name": name,
            }.items()
            if value is not None
        }
        signals: list[IoSignal] = []
        start = 0
        while True:
            params = {"start": str(start), "limit": str(page_size)}
            if filters:
                payload = self._client.post_json(
                    "/rw/iosystem/signals/signal-search",
                    data=filters,
                    params=params,
                )
            else:
                payload = self._client.get_json("/rw/iosystem/signals", params=params)

            resources = embedded_resources(payload, resource="I/O signals")
            for item in resources:
                if item.get("_type") != "ios-signal-li":
                    continue
                title = required_text(item, "_title", resource="I/O signal")
                path_parts = title.split("/", 2)
                item_network = path_parts[0] if len(path_parts) == 3 else None
                item_device = path_parts[1] if len(path_parts) == 3 else None
                signals.append(
                    IoSignal(
                        network=item_network,
                        device=item_device,
                        name=required_text(item, "name", resource="I/O signal"),
                        signal_type=required_text(item, "type", resource="I/O signal"),
                        category=required_string(
                            item, "category", resource="I/O signal"
                        ),
                        value=required_text(item, "lvalue", resource="I/O signal"),
                        state=required_text(item, "lstate", resource="I/O signal"),
                    )
                )

            if not has_next_link(payload, resource="I/O signals"):
                return signals
            start += page_size

    def get_signal(self, network: str, device: str, name: str) -> IoSignalDetails:
        path = "/rw/iosystem/signals/{}/{}/{}".format(
            quote(network, safe=""), quote(device, safe=""), quote(name, safe="")
        )
        resources = embedded_resources(
            self._client.get_json(path),
            resource=f"I/O signal {network}/{device}/{name}",
        )
        matches = [item for item in resources if item.get("_type") == "ios-signal-li"]
        if not matches:
            raise ProtocolError(
                f"I/O signal {network}/{device}/{name}: response has no signal resource"
            )
        item = matches[0]
        return IoSignalDetails(
            network=network,
            device=device,
            name=required_text(item, "name", resource="I/O signal"),
            signal_type=required_text(item, "type", resource="I/O signal"),
            category=required_string(item, "category", resource="I/O signal"),
            logical_value=required_text(item, "lvalue", resource="I/O signal"),
            logical_state=required_text(item, "lstate", resource="I/O signal"),
            physical_value=required_text(item, "pvalue", resource="I/O signal"),
            physical_state=required_text(item, "phstate", resource="I/O signal"),
            quality=required_text(item, "quality", resource="I/O signal"),
            access_level=required_text(item, "access-level", resource="I/O signal"),
            write_access=required_text(item, "write-access", resource="I/O signal"),
            safety_level=required_text(item, "safe-level", resource="I/O signal"),
        )
