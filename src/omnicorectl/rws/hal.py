"""Small, tolerant helpers for ABB's HAL+JSON representations."""

from __future__ import annotations

from typing import Any

from omnicorectl.errors import ProtocolError


def first_state(payload: Any, *, resource: str) -> dict[str, Any]:
    """Return the first object in an RWS ``state`` collection.

    RWS response schemas are intentionally treated as additive mappings. Unknown
    keys survive parsing, while the minimum shape used by a service is checked.
    """

    if not isinstance(payload, dict):
        raise ProtocolError(f"{resource}: expected a JSON object")

    state = payload.get("state")
    if not isinstance(state, list) or not state or not isinstance(state[0], dict):
        raise ProtocolError(f"{resource}: response has no state resource")
    return state[0]


def required_text(state: dict[str, Any], key: str, *, resource: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{resource}: missing text field {key!r}")
    return value


def embedded_resources(payload: Any, *, resource: str) -> list[dict[str, Any]]:
    """Return object entries from an RWS HAL ``_embedded.resources`` list."""

    if not isinstance(payload, dict):
        raise ProtocolError(f"{resource}: expected a JSON object")
    embedded = payload.get("_embedded")
    if not isinstance(embedded, dict):
        raise ProtocolError(f"{resource}: response has no embedded resources")
    resources = embedded.get("resources")
    if not isinstance(resources, list):
        raise ProtocolError(f"{resource}: embedded resources is not a list")
    if not all(isinstance(item, dict) for item in resources):
        raise ProtocolError(f"{resource}: embedded resource is not an object")
    return resources


def required_bool(state: dict[str, Any], key: str, *, resource: str) -> bool:
    value = required_text(state, key, resource=resource).strip().lower()
    if value in {"true", "on", "1"}:
        return True
    if value in {"false", "off", "0"}:
        return False
    raise ProtocolError(f"{resource}: invalid boolean field {key!r}: {value!r}")
