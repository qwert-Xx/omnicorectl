"""Controller configuration database resources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from omnicorectl.errors import ConfigurationError, ProtocolError, RwsHttpError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import (
    embedded_resources,
    first_state,
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


@dataclass(frozen=True, slots=True)
class CfgChange:
    domain: str
    cfg_type: str
    instance: str
    attribute: str
    old_value: str
    new_value: str
    changed: bool
    validated: bool
    restart_required: bool


@dataclass(frozen=True, slots=True)
class CfgCreation:
    domain: str
    cfg_type: str
    instance: str
    instance_id: str
    attributes: dict[str, str]
    validated: bool
    restart_required: bool


@dataclass(frozen=True, slots=True)
class CfgDeletion:
    domain: str
    cfg_type: str
    instance: str
    instance_id: str
    validated: bool
    restart_required: bool


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
                instances.append(_parse_instance(item, domain, cfg_type))

            if not has_next_link(payload, resource="CFG instances"):
                return instances
            start += page_size

    def get_instance(self, domain: str, cfg_type: str, instance: str) -> CfgInstance:
        path = "/rw/cfg/{}/{}/instances/{}".format(
            quote(domain, safe=""),
            quote(cfg_type, safe=""),
            quote(instance, safe=""),
        )
        item = first_state(
            self._client.get_json(path),
            resource=f"CFG instance {domain}/{cfg_type}/{instance}",
        )
        if item.get("_type") != "cfg-dt-instance":
            raise ProtocolError(
                f"CFG instance {domain}/{cfg_type}/{instance}: unexpected resource type"
            )
        return _parse_instance(item, domain, cfg_type)

    def set_attribute(
        self,
        domain: str,
        cfg_type: str,
        instance: str,
        attribute: str,
        value: str,
        *,
        element_count: int = 1,
    ) -> CfgChange:
        if element_count <= 0:
            raise ConfigurationError("CFG element count must be positive")
        before = self.get_instance(domain, cfg_type, instance)
        if before.read_only:
            raise ConfigurationError(
                f"CFG instance is read only: {domain}/{cfg_type}/{instance}"
            )
        if attribute not in before.attributes:
            raise ConfigurationError(
                f"CFG attribute does not exist on {instance}: {attribute}"
            )
        old_value = before.attributes[attribute]
        if old_value == value:
            return CfgChange(
                domain=domain,
                cfg_type=cfg_type,
                instance=before.name,
                attribute=attribute,
                old_value=old_value,
                new_value=value,
                changed=False,
                validated=True,
                restart_required=False,
            )

        endpoint = _instance_endpoint(domain, cfg_type, instance)
        self._post_attribute(endpoint, attribute, value, element_count)
        try:
            self._validate_instance(domain, cfg_type, instance)
            after = self.get_instance(domain, cfg_type, instance)
            new_value = after.attributes.get(attribute)
            if new_value != value:
                raise ProtocolError(
                    f"CFG update verification failed: expected {attribute}={value!r}, "
                    f"controller reports {new_value!r}"
                )
        except Exception as original_error:
            try:
                self._post_attribute(endpoint, attribute, old_value, element_count)
                self._validate_instance(domain, cfg_type, instance)
                restored = self.get_instance(domain, cfg_type, instance)
                if restored.attributes.get(attribute) != old_value:
                    raise ProtocolError(
                        f"rollback verification reports "
                        f"{attribute}={restored.attributes.get(attribute)!r}"
                    )
            except Exception as rollback_error:
                raise ProtocolError(
                    "CFG update failed and automatic rollback also failed: "
                    f"{rollback_error}"
                ) from original_error
            raise ProtocolError(
                f"CFG update failed; original value was restored: {original_error}"
            ) from original_error

        return CfgChange(
            domain=domain,
            cfg_type=cfg_type,
            instance=after.name,
            attribute=attribute,
            old_value=old_value,
            new_value=value,
            changed=True,
            validated=True,
            restart_required=True,
        )

    def create_instance(
        self,
        domain: str,
        cfg_type: str,
        instance: str,
        attributes: dict[str, str] | None = None,
    ) -> CfgCreation:
        """Create, configure, validate, and verify one external CFG instance.

        RobotWare creates an instance with type defaults first. Attribute values are
        then sent as one update so the controller only validates the intended final
        state. Any failure removes the newly created instance again.
        """

        name = instance.strip()
        if not name:
            raise ConfigurationError("CFG instance name cannot be empty")
        if self._instance_exists(domain, cfg_type, name):
            raise ConfigurationError(
                f"CFG instance already exists: {domain}/{cfg_type}/{name}"
            )

        requested = dict(attributes or {})
        if "Name" in requested and requested["Name"] != name:
            raise ConfigurationError(
                "the Name attribute must match the CFG instance name"
            )

        collection = "/rw/cfg/{}/{}/instances/create-default".format(
            quote(domain, safe=""), quote(cfg_type, safe="")
        )
        created = False
        try:
            self._client.post_form(collection, {"name": name})
            created = True
            default_instance = self.get_instance(domain, cfg_type, name)
            unknown = sorted(set(requested) - set(default_instance.attributes))
            if unknown:
                raise ConfigurationError(
                    f"CFG attributes do not exist on {name}: {', '.join(unknown)}"
                )
            if requested:
                self._post_attributes(
                    _instance_endpoint(domain, cfg_type, name), requested
                )
            self._validate_instance(domain, cfg_type, name)
            after = self.get_instance(domain, cfg_type, name)
            mismatches = {
                key: after.attributes.get(key)
                for key, value in requested.items()
                if after.attributes.get(key) != value
            }
            if mismatches:
                details = ", ".join(
                    f"{key}={value!r}" for key, value in mismatches.items()
                )
                raise ProtocolError(
                    f"CFG create verification failed for {name}: {details}"
                )
        except Exception as original_error:
            if created:
                try:
                    self._client.delete(_instance_endpoint(domain, cfg_type, name))
                    if self._instance_exists(domain, cfg_type, name):
                        raise ProtocolError(
                            "created instance still exists after rollback"
                        )
                except Exception as rollback_error:
                    raise ProtocolError(
                        "CFG create failed and automatic rollback also failed: "
                        f"{rollback_error}"
                    ) from original_error
            if isinstance(original_error, ConfigurationError):
                raise
            raise ProtocolError(
                f"CFG create failed; the new instance was removed: {original_error}"
            ) from original_error

        return CfgCreation(
            domain=domain,
            cfg_type=cfg_type,
            instance=after.name,
            instance_id=after.instance_id,
            attributes=after.attributes,
            validated=True,
            restart_required=True,
        )

    def delete_instance(self, domain: str, cfg_type: str, instance: str) -> CfgDeletion:
        before = self.get_instance(domain, cfg_type, instance)
        if before.read_only:
            raise ConfigurationError(
                f"CFG instance is read only: {domain}/{cfg_type}/{instance}"
            )
        self._validate_instance(domain, cfg_type, instance, operation=1)
        self._client.delete(_instance_endpoint(domain, cfg_type, instance))
        if self._instance_exists(domain, cfg_type, instance):
            raise ProtocolError(
                f"CFG delete verification failed: {domain}/{cfg_type}/{instance}"
            )
        return CfgDeletion(
            domain=domain,
            cfg_type=cfg_type,
            instance=before.name,
            instance_id=before.instance_id,
            validated=True,
            restart_required=True,
        )

    def _post_attribute(
        self,
        endpoint: str,
        attribute: str,
        value: str,
        element_count: int,
    ) -> None:
        self._client.post_form(endpoint, {attribute: f"[{value},{element_count}]"})

    def _post_attributes(self, endpoint: str, attributes: dict[str, str]) -> None:
        self._client.post_form(
            endpoint, {key: f"[{value},1]" for key, value in attributes.items()}
        )

    def _validate_instance(
        self, domain: str, cfg_type: str, instance: str, *, operation: int = 0
    ) -> None:
        if operation not in {0, 1}:
            raise ConfigurationError("CFG validation operation must be 0 or 1")
        payload = self._client.post_form_optional_json(
            "/rw/cfg/validate-instances",
            {
                "operation": str(operation),
                "cfgdomain": domain,
                "cfgtype": cfg_type,
                "instances": f"[{instance}]",
            },
        )
        if payload is None:
            return
        status = payload.get("status")
        if not isinstance(status, dict):
            raise ProtocolError("CFG validation: expected status object")
        valid = status.get("valid")
        if valid is True or (isinstance(valid, str) and valid.lower() == "true"):
            return
        code = status.get("code", "unknown")
        message = status.get("msg", "validation failed")
        raise ProtocolError(f"CFG validation failed (ABB {code}: {message})")

    def _instance_exists(self, domain: str, cfg_type: str, instance: str) -> bool:
        try:
            self.get_instance(domain, cfg_type, instance)
        except RwsHttpError as exc:
            if exc.status_code == 404:
                return False
            raise
        return True


def _instance_endpoint(domain: str, cfg_type: str, instance: str) -> str:
    return "/rw/cfg/{}/{}/instances/{}".format(
        quote(domain, safe=""),
        quote(cfg_type, safe=""),
        quote(instance, safe=""),
    )


def _parse_instance(item: dict[str, object], domain: str, cfg_type: str) -> CfgInstance:
    attributes_raw = item.get("attrib")
    if not isinstance(attributes_raw, list):
        raise ProtocolError("CFG instance: attributes is not a list")
    attributes: dict[str, str] = {}
    for attribute in attributes_raw:
        if not isinstance(attribute, dict):
            raise ProtocolError("CFG instance: attribute is not an object")
        if attribute.get("_type") != "cfg-ia-t":
            continue
        key = required_text(attribute, "_title", resource="CFG attribute")
        attributes[key] = required_string(attribute, "value", resource="CFG attribute")

    raw_instance_id = item.get("instanceid")
    if isinstance(raw_instance_id, bool) or not isinstance(raw_instance_id, (str, int)):
        raise ProtocolError("CFG instance: invalid instanceid")
    return CfgInstance(
        domain=domain,
        cfg_type=cfg_type,
        name=required_text(item, "_title", resource="CFG instance"),
        instance_id=str(raw_instance_id),
        read_only=required_bool(item, "rdonly", resource="CFG instance"),
        attributes=attributes,
    )
