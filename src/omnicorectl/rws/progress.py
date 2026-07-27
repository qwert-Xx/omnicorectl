"""Polling support for Robot Web Services asynchronous operations.

Robot Web Services 异步操作的轮询支持。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from omnicorectl.errors import ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_text


@dataclass(frozen=True, slots=True)
class ProgressResult:
    uri: str
    state: str
    code: str
    resource_path: str


class ProgressService:
    def __init__(
        self,
        client: RwsClient,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._clock = clock
        self._sleep = sleep

    def wait(
        self,
        progress_uri: str,
        *,
        timeout: float,
        poll_interval: float,
    ) -> ProgressResult:
        if timeout <= 0:
            raise ProtocolError("progress timeout must be positive")
        if poll_interval <= 0:
            raise ProtocolError("progress polling interval must be positive")
        deadline = self._clock() + timeout
        while True:
            result = _parse_progress(progress_uri, self._client.get_json(progress_uri))
            if result.state.lower() != "pending":
                return result
            if self._clock() >= deadline:
                raise ProtocolError(
                    f"operation did not complete within {timeout:g} seconds; "
                    f"progress remains at {progress_uri}"
                )
            self._sleep(min(poll_interval, max(0.0, deadline - self._clock())))


def _parse_progress(progress_uri: str, payload: dict[str, object]) -> ProgressResult:
    item = first_state(payload, resource=f"progress {progress_uri}")
    state = required_text(item, "state", resource="RWS progress")
    code = required_text(item, "code", resource="RWS progress")
    resource_path = ""
    links = item.get("_links")
    if isinstance(links, dict):
        resource = links.get("resource")
        if isinstance(resource, dict):
            href = resource.get("href")
            if isinstance(href, str):
                resource_path = href
    return ProgressResult(progress_uri, state, code, resource_path)
