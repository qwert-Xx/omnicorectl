"""Small, tolerant helpers for ABB HAL+JSON representations.

用于解析 ABB HAL+JSON 表示形式的小型宽容型辅助函数。
"""

from __future__ import annotations

from typing import Any

from omnicorectl.errors import ProtocolError


def first_state(payload: Any, *, resource: str) -> dict[str, Any]:
    """Return the first object in an RWS ``state`` collection.

    RWS response schemas are intentionally treated as additive mappings. Unknown
    keys survive parsing, while the minimum shape used by a service is checked.
    RWS 响应模式被视为可扩展映射：未知键会被保留，同时检查服务所需的最小结构。
    """

    state = state_resources(payload, resource=resource)
    if not state:
        raise ProtocolError(f"{resource}: response has no state resource")
    return state[0]


def state_resources(payload: Any, *, resource: str) -> list[dict[str, Any]]:
    """Return objects from an RWS top-level ``state`` list.

    返回 RWS 顶层 ``state`` 列表中的对象条目。
    """

    if not isinstance(payload, dict):
        raise ProtocolError(f"{resource}: expected a JSON object")
    state = payload.get("state")
    if not isinstance(state, list):
        raise ProtocolError(f"{resource}: response state is not a list")
    if not all(isinstance(item, dict) for item in state):
        raise ProtocolError(f"{resource}: state resource is not an object")
    return state


def required_text(state: dict[str, Any], key: str, *, resource: str) -> str:
    value = required_string(state, key, resource=resource)
    if not value:
        raise ProtocolError(f"{resource}: missing text field {key!r}")
    return value


def required_string(state: dict[str, Any], key: str, *, resource: str) -> str:
    """Read a string field while allowing an empty value.

    读取字符串字段，并允许空字符串作为合法值。
    """

    value = state.get(key)
    if not isinstance(value, str):
        raise ProtocolError(f"{resource}: missing string field {key!r}")
    return value


def embedded_resources(payload: Any, *, resource: str) -> list[dict[str, Any]]:
    """Return objects from an RWS HAL ``_embedded.resources`` list.

    返回 RWS HAL ``_embedded.resources`` 列表中的对象条目。
    """

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


def required_int(state: dict[str, Any], key: str, *, resource: str) -> int:
    value = state.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProtocolError(f"{resource}: invalid integer field {key!r}")
    try:
        return int(value.strip() if isinstance(value, str) else value)
    except ValueError as exc:
        raise ProtocolError(f"{resource}: invalid integer field {key!r}") from exc


def has_next_link(payload: Any, *, resource: str) -> bool:
    """Return whether an RWS HAL page advertises a following page.

    返回 RWS HAL 页面是否声明了下一页。
    """

    if not isinstance(payload, dict):
        raise ProtocolError(f"{resource}: expected a JSON object")
    links = payload.get("_links")
    if links is None:
        return False
    if not isinstance(links, dict):
        raise ProtocolError(f"{resource}: response links is not an object")
    next_link = links.get("next")
    if next_link is None:
        return False
    if not isinstance(next_link, dict) or not isinstance(next_link.get("href"), str):
        raise ProtocolError(f"{resource}: invalid next-page link")
    return True
