"""Read-only I/O system resources."""

from __future__ import annotations

from dataclasses import dataclass

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import embedded_resources, required_text


@dataclass(frozen=True, slots=True)
class IoNetwork:
    name: str
    physical_state: str
    logical_state: str


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
