from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.rapid_debug import RapidDebugService


class RapidDebugTests(unittest.TestCase):
    def test_accepts_rw81_execution_shape_without_hold_to_run(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "_type": "rap-execution",
                            "ctrlexecstate": "stopped",
                            "cycle": "forever",
                        }
                    ]
                },
            )

        with _client(handler) as client:
            state = RapidDebugService(client).execution_state()
        self.assertEqual(state.cycle, "forever")
        self.assertIsNone(state.hold_to_run)

    def test_execution_state_start_stop_and_reset(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.url.path == "/rw/rapid/execution" and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "ctrlexecstate": "stopped",
                                "rapidexeccycle": "once",
                                "holdtorun": "false",
                            }
                        ]
                    },
                )
            calls.append(request)
            return httpx.Response(204)

        with _client(handler) as client:
            service = RapidDebugService(client)
            state = service.execution_state()
            service.start_execution(execution_mode="stepover", cycle="once")
            service.stop_execution(stop_mode="qstop", all_tasks=True)
            service.reset_all_program_pointers()

        self.assertEqual(state.state, "stopped")
        self.assertFalse(state.hold_to_run)
        self.assertEqual(calls[0].url.path, "/rw/rapid/execution/start")
        self.assertEqual(parse_qs(calls[0].content.decode())["execmode"], ["stepover"])
        self.assertEqual(calls[1].url.path, "/rw/rapid/execution/stop")
        self.assertEqual(parse_qs(calls[1].content.decode())["usetsp"], ["alltsk"])
        self.assertEqual(calls[2].url.path, "/rw/rapid/execution/resetpp")
        self.assertTrue(
            all(call.url.params["mastership"] == "implicit" for call in calls)
        )

    def test_program_pointer_read_and_mutations(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "pcp-info",
                                "_title": "progpointer",
                                "beginposition": "9,8",
                                "endposition": "9,20",
                                "modulename": "MainModule",
                                "routinename": "main",
                                "changecount": "12",
                                "executiontype": "normal",
                            },
                            {
                                "_type": "pcp-info",
                                "_title": "motionpointer",
                                "beginposition": "10,1",
                                "endposition": "10,8",
                                "modulename": "MainModule",
                                "routinename": "main",
                                "executiontype": "normal",
                            },
                        ]
                    },
                )
            calls.append(request)
            return httpx.Response(204)

        with _client(handler) as client:
            service = RapidDebugService(client)
            pointers = service.get_program_pointers("T_ROB1")
            service.set_program_pointer_cursor("T_ROB1", "MainModule", 12, 3)
            service.set_program_pointer_routine("T_ROB1", "MainModule", "main")
            service.move_program_pointer("T_ROB1", "next")
            service.move_program_pointer("T_ROB1", "previous")
            service.reset_program_pointer("T_ROB1")

        self.assertEqual(len(pointers), 2)
        self.assertEqual(pointers[0].begin_column, 8)
        self.assertIsNone(pointers[1].change_count)
        self.assertEqual(calls[0].url.path, "/rw/rapid/tasks/T_ROB1/pcp/cursor")
        self.assertEqual(parse_qs(calls[0].content.decode())["line"], ["12"])
        self.assertTrue(calls[-1].url.path.endswith("/pcp/reset"))

    def test_unavailable_rw81_program_pointers_return_an_empty_list(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "_type": "pcp-info",
                            "_title": "progpointer",
                            "progpointer": {
                                "_links": {"error": {"href": "/rw/retcode"}}
                            },
                        },
                        {
                            "_type": "pcp-info",
                            "_title": "motionpointer",
                            "motionpointer": {
                                "_links": {"error": {"href": "/rw/retcode"}}
                            },
                        },
                    ]
                },
            )

        with _client(handler) as client:
            pointers = RapidDebugService(client).get_program_pointers("T_ROB1")
        self.assertEqual(pointers, [])

    def test_breakpoint_lifecycle(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rap-program-breakpoint",
                                "module-name": "MainModule",
                                "start-row": "11",
                                "start-col": "3",
                                "end-row": "11",
                                "end-col": "31",
                            }
                        ]
                    },
                )
            calls.append(request)
            if request.url.path.endswith("/breakpoints"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "start-row": "15",
                                "start-col": "3",
                                "end-row": "15",
                                "end-col": "31",
                            }
                        ]
                    },
                )
            return httpx.Response(204)

        with _client(handler) as client:
            service = RapidDebugService(client)
            listing = service.list_breakpoints("T_ROB1")
            created = service.set_breakpoint("T_ROB1", "MainModule", 15, 3)
            service.clear_breakpoint("T_ROB1", all_breakpoints=True)

        self.assertEqual(listing[0].end_column, 31)
        self.assertEqual(created.start_row, 15)
        self.assertEqual(calls[-1].url.params["all"], "true")

    def test_symbol_search_read_write_and_validation(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/rw/rapid/symbols/search":
                form = parse_qs(request.content.decode())
                self.assertEqual(form["blockurl"], ["RAPID/T_ROB1"])
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rap-symproppers-li",
                                "symburl": "RAPID/T_ROB1/MainModule/counter",
                                "name": "counter",
                                "symtyp": "per",
                                "dattyp": "num",
                                "dim": "",
                                "local": "false",
                                "rdonly": "false",
                                "taskpers": "false",
                                "typurl": "RAPID/num",
                            }
                        ]
                    },
                )
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {"_type": "rap-data", "value": "42"},
                            {
                                "_type": "rap-data-decl-pos",
                                "begin-row": "8",
                                "begin-coloumn": "2",
                                "end-row": "8",
                                "end-coloumn": "20",
                            },
                        ]
                    },
                )
            calls.append(request)
            return httpx.Response(204)

        symbol_url = "RAPID/T_ROB1/MainModule/counter"
        with _client(handler) as client:
            service = RapidDebugService(client)
            symbols = service.search_symbols(block_url="RAPID/T_ROB1")
            data = service.get_symbol_data(symbol_url)
            service.set_symbol_data(symbol_url, "43", initial_value=True)
            service.validate_symbol_value("T_ROB1", "num", "43")

        self.assertEqual(symbols[0].data_type, "num")
        self.assertEqual(data.value, "42")
        self.assertEqual(data.declaration_begin_row, 8)
        self.assertEqual(calls[0].url.params["initval"], "true")
        self.assertEqual(calls[0].url.params["mastership"], "implicit")
        self.assertEqual(calls[1].url.path, "/rw/rapid/symbols/validate")

    def test_reads_mechanical_units_and_current_targets(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/mechunits"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rapid-mechunit",
                                "name": "ROB_1",
                                "mode": "active",
                                "type": "tcp_robot",
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/robtarget"):
                self.assertEqual(request.url.params["tool"], "tool0")
                values = {
                    "x": "1",
                    "y": "2",
                    "z": "3",
                    "q1": "1",
                    "q2": "0",
                    "q3": "0",
                    "q4": "0",
                    "cf1": "0",
                    "cf4": "0",
                    "cf6": "0",
                    "cfx": "0",
                    **{f"eax_{axis}": "9E9" for axis in "abcdef"},
                }
                return httpx.Response(200, json={"state": [values]})
            values = {
                **{f"rax_{axis}": str(axis) for axis in range(1, 7)},
                **{f"eax_{axis}": "9E9" for axis in "abcdef"},
            }
            return httpx.Response(200, json={"state": [values]})

        with _client(handler) as client:
            service = RapidDebugService(client)
            units = service.list_mechanical_units("T_ROB1")
            robot_target = service.get_robot_target(
                "T_ROB1", tool="tool0", work_object="wobj0"
            )
            joint_target = service.get_joint_target("T_ROB1")

        self.assertEqual(units[0].name, "ROB_1")
        self.assertEqual(robot_target.translation, ("1", "2", "3"))
        self.assertEqual(joint_target.robot_axes[-1], "6")


def _client(handler: object) -> RwsClient:
    return RwsClient(
        "192.0.2.1",
        "test-user",
        "test-password",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        request_interval=0,
    )


if __name__ == "__main__":
    unittest.main()
