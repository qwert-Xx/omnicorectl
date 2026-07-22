"""Read-only controller configuration database resources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import embedded_resources, required_text


@dataclass(frozen=True, slots=True)
class CfgDomain:
    name: str


@dataclass(frozen=True, slots=True)
class CfgType:
    domain: str
    name: str


class CfgService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def list_domains(self) -> list[CfgDomain]:
        resources = embedded_resources(
            self._client.get_json("/rw/cfg"), resource="CFG domains"
        )
        return [
            CfgDomain(name=required_text(item, "_title", resource="CFG domain"))
            for item in resources
            if item.get("_type") == "cfg-domain-li"
        ]

    def list_types(self, domain: str) -> list[CfgType]:
        resources = embedded_resources(
            self._client.get_json(f"/rw/cfg/{quote(domain, safe='')}"),
            resource=f"CFG types in {domain}",
        )
        return [
            CfgType(
                domain=domain,
                name=required_text(item, "_title", resource="CFG type"),
            )
            for item in resources
            if item.get("_type") == "cfg-dt-li"
        ]
