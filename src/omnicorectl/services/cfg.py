"""Read-only controller configuration database resources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from omnicorectl.rws.client import RwsClient
from omnicorectl.errors import ProtocolError
from omnicorectl.rws.hal import (
    embedded_resources,
    has_next_link,
    required_bool,
    required_string,
    required_text,
)


@dataclass(frozen=True, slots=True)
class CfgDomain:
    name: str


@dataclass(frozen=True, slots=True)
class CfgType:
    domain: str
    name: str


@dataclass(frozen=True, slots=True)
class CfgInstance:
    domain: str
    cfg_type: str
    name: str
    instance_id: str
    read_only: bool
    attributes: dict[str, str]


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

    def list_instances(
        self, domain: str, cfg_type: str, *, page_size: int = 200
    ) -> list[CfgInstance]:
        domain_path = quote(domain, safe="")
        type_path = quote(cfg_type, safe="")
        path = f"/rw/cfg/{domain_path}/{type_path}/instances"
        instances: list[CfgInstance] = []
        start = 0
        while True:
            payload = self._client.get_json(
                path, params={"start": str(start), "limit": str(page_size)}
            )
            resources = embedded_resources(
                payload, resource=f"CFG instances {domain}/{cfg_type}"
            )
            for item in resources:
                if item.get("_type") != "cfg-dt-instance-li":
                    continue
                attributes_raw = item.get("attrib")
                if not isinstance(attributes_raw, list):
                    raise ProtocolError("CFG instance: attributes is not a list")
                attributes: dict[str, str] = {}
                for attribute in attributes_raw:
                    if not isinstance(attribute, dict):
                        raise ProtocolError("CFG instance: attribute is not an object")
                    if attribute.get("_type") != "cfg-ia-t":
                        continue
                    key = required_text(
                        attribute, "_title", resource="CFG attribute"
                    )
                    attributes[key] = required_string(
                        attribute, "value", resource="CFG attribute"
                    )
                instances.append(
                    CfgInstance(
                        domain=domain,
                        cfg_type=cfg_type,
                        name=required_text(
                            item, "_title", resource="CFG instance"
                        ),
                        instance_id=required_text(
                            item, "instanceid", resource="CFG instance"
                        ),
                        read_only=required_bool(
                            item, "rdonly", resource="CFG instance"
                        ),
                        attributes=attributes,
                    )
                )

            if not has_next_link(payload, resource="CFG instances"):
                return instances
            start += page_size
