"""Synchronous, session-oriented RWS 2.0 HTTP client."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, BinaryIO

import httpx

from omnicorectl.errors import (
    AuthenticationError,
    AuthorizationError,
    NetworkError,
    ProtocolError,
    RwsHttpError,
)

HAL_JSON_V2 = "application/hal+json;v=2.0"
FORM_V2 = "application/x-www-form-urlencoded;v=2.0"


class RwsClient:
    """Own one authenticated RWS session for the duration of a CLI command."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_tls: bool = True,
        timeout: float = 10.0,
        request_interval: float = 0.055,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        if "://" not in normalized_url:
            normalized_url = f"https://{normalized_url}"

        self._request_interval = request_interval
        self._last_request_at: float | None = None
        self._clock = clock
        self._sleep = sleep
        self._closed = False
        self._client = httpx.Client(
            base_url=normalized_url,
            auth=httpx.BasicAuth(username, password),
            headers={"Accept": HAL_JSON_V2},
            verify=verify_tls,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self) -> "RwsClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_json(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        response = self._request("GET", path, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProtocolError(f"{path}: controller did not return JSON") from exc
        if not isinstance(payload, dict):
            raise ProtocolError(f"{path}: expected a JSON object")
        return payload

    def post_json(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            path,
            params=params,
            data=data,
            headers={"Content-Type": FORM_V2},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProtocolError(f"{path}: controller did not return JSON") from exc
        if not isinstance(payload, dict):
            raise ProtocolError(f"{path}: expected a JSON object")
        return payload

    def download(self, path: str, destination: BinaryIO) -> int:
        """Stream a controller resource to an already-open binary destination."""

        self._throttle()
        total = 0
        try:
            with self._client.stream("GET", path) as response:
                self._raise_for_status(response, "GET", path)
                for chunk in response.iter_bytes():
                    destination.write(chunk)
                    total += len(chunk)
        except httpx.TimeoutException as exc:
            raise NetworkError(f"request timed out: GET {path}") from exc
        except httpx.RequestError as exc:
            raise NetworkError(f"controller connection failed: {exc}") from exc
        return total

    def close(self) -> None:
        if self._closed:
            return
        # Releasing the server-side session avoids exhausting the controller's
        # finite session pool. Logout is best-effort so it cannot hide the result
        # of the user's command.
        try:
            self._request("GET", "/logout")
        except Exception:
            pass
        finally:
            self._client.close()
            self._closed = True

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self._throttle()
        try:
            response = self._client.request(
                method, path, params=params, data=data, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise NetworkError(f"request timed out: {method} {path}") from exc
        except httpx.RequestError as exc:
            raise NetworkError(f"controller connection failed: {exc}") from exc

        self._raise_for_status(response, method, path)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response, method: str, path: str) -> None:
        if response.status_code == 401:
            raise AuthenticationError("controller rejected the username or password")
        if response.status_code == 403:
            raise AuthorizationError(f"controller denied access to {path}")
        if response.is_error:
            raise RwsHttpError(
                response.status_code,
                f"RWS {method} {path} returned HTTP {response.status_code}",
            )

    def _throttle(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self._request_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_request_at = now
