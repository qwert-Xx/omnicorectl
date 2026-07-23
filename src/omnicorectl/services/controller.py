"""Controller information and lifecycle workflows.

控制器信息与生命周期工作流。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import first_state, required_int, required_text


@dataclass(frozen=True, slots=True)
class ControllerStatus:
    name: str
    controller_id: str
    controller_type: str
    mac_address: str
    operation_mode: str
    controller_state: str
    rapid_execution: str
    execution_cycle: str


@dataclass(frozen=True, slots=True)
class RestartResult:
    mode: str
    accepted: bool
    restart_count_before: int


@dataclass(frozen=True, slots=True)
class MotorStateChange:
    requested_state: str
    state_before: str
    state_after: str
    changed: bool


class ControllerService:
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

    def status(self) -> ControllerStatus:
        identity = first_state(
            self._client.get_json("/ctrl/identity"), resource="controller identity"
        )
        operation_mode = first_state(
            self._client.get_json("/rw/panel/opmode"), resource="operation mode"
        )
        controller_state = self.controller_state()
        execution = first_state(
            self._client.get_json("/rw/rapid/execution"),
            resource="RAPID execution",
        )

        return ControllerStatus(
            name=required_text(identity, "ctrl-name", resource="controller identity"),
            controller_id=required_text(
                identity, "ctrl-id", resource="controller identity"
            ),
            controller_type=required_text(
                identity, "ctrl-type", resource="controller identity"
            ),
            mac_address=required_text(
                identity, "ctrl-mac", resource="controller identity"
            ),
            operation_mode=required_text(
                operation_mode, "opmode", resource="operation mode"
            ),
            controller_state=controller_state,
            rapid_execution=required_text(
                execution, "ctrlexecstate", resource="RAPID execution"
            ),
            execution_cycle=required_text(
                execution, "cycle", resource="RAPID execution"
            ),
        )

    def controller_state(self) -> str:
        state = first_state(
            self._client.get_json("/rw/panel/ctrl-state"),
            resource="controller state",
        )
        return required_text(state, "ctrlstate", resource="controller state").lower()

    def set_motor_state(
        self,
        requested_state: str,
        *,
        wait_timeout: float = 8.0,
        poll_interval: float = 0.25,
    ) -> MotorStateChange:
        """Set Motors On/Off and verify the resulting controller state.

        设置电机开/关，并回读验证最终控制器状态。
        """

        target = requested_state.strip().lower()
        if target not in {"motoron", "motoroff"}:
            raise ConfigurationError(
                "motor state must be either 'motoron' or 'motoroff'"
            )
        if wait_timeout <= 0 or poll_interval <= 0:
            raise ConfigurationError(
                "motor-state wait timeout and poll interval must be positive"
            )

        before = self.controller_state()
        if before == target:
            return MotorStateChange(target, before, before, False)

        required_before = "motoroff" if target == "motoron" else "motoron"
        if before != required_before:
            raise ConfigurationError(
                f"cannot request {target} while controller state is {before}; "
                f"expected {required_before}"
            )

        self._client.post_form(
            "/rw/panel/ctrl-state",
            {"ctrl-state": target},
        )
        deadline = self._clock() + wait_timeout
        current = before
        unsafe_states = {
            "guardstop",
            "emergencystop",
            "emergencystopreset",
            "sysfail",
        }
        while self._clock() < deadline:
            current = self.controller_state()
            if current == target:
                return MotorStateChange(target, before, current, True)
            if target == "motoron" and current in unsafe_states:
                raise ProtocolError(
                    f"Motors On transition stopped in controller state {current}"
                )
            self._sleep(poll_interval)

        raise ProtocolError(
            f"timed out waiting for controller state {target}; last state was {current}"
        )

    def restart_count(self) -> int:
        state = first_state(
            self._client.get_json("/ctrl/restart/restartcount"),
            resource="controller restart count",
        )
        return required_int(state, "restart-count", resource="controller restart count")

    def warm_restart(self) -> RestartResult:
        restart_count = self.restart_count()
        self._client.post_form(
            "/ctrl/restart",
            {"restart-mode": "restart"},
            params={"mastership": "implicit"},
        )
        return RestartResult(
            mode="restart",
            accepted=True,
            restart_count_before=restart_count,
        )
