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

