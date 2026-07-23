from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from omnicorectl.errors import ConfigurationError
from omnicorectl.rws import RwsClient
from omnicorectl.services.rapid import RapidService


class RapidMutationTests(unittest.TestCase):
    def test_reads_module_metadata_and_searches_text(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/rw/rapid/tasks/T_ROB1/modules/MainModule":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {"_type": "link"},
                            {
                                "_type": "rap-module",
                                "modname": "MainModule",
                                "filename": "MainModule.mod",
                                "attribute": "readonly,noview",
                            },
                        ]
                    },
                )
            if request.url.path.endswith("/module-extension"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rap-module-extension",
                                "num-of-lines": "24",
                                "max-num-of-col": "118",
                                "count": "680609",
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/text/search"):
                self.assertEqual(request.url.params["text"], "main")
                return httpx.Response(
                    200,
                    json={"state": [{"Row": "5", "Column": "8"}]},
                )
            return httpx.Response(200, json={})

        with _client(handler) as client:
            service = RapidService(client)
            attributes = service.get_module_attributes("T_ROB1", "MainModule")
            extension = service.get_module_extension("T_ROB1", "MainModule")
            position = service.search_text("T_ROB1", "MainModule", "main")

        self.assertTrue(attributes.read_only)
        self.assertEqual(extension.lines, 24)
        self.assertIsNotNone(position)
        self.assertEqual(position.row, 5)  # type: ignore[union-attr]

    def test_sets_complete_module_with_implicit_mastership_and_change_guard(
        self,
    ) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            if request.url.path.endswith("/changecount"):
                calls += 1
                return httpx.Response(200, json={"state": [{"count": "7"}]})
            if request.url.path.endswith("/text") and request.method == "POST":
                self.assertEqual(request.url.params["mastership"], "implicit")
                self.assertEqual(
                    parse_qs(request.content.decode())["text"],
                    ["MODULE MainModule\nENDMODULE\n"],
                )
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "module-changed-name": "FALSE",
                                "new-modnam": "",
                                "change-count": "8",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={})

        with _client(handler) as client:
            change = RapidService(client).set_module_text(
                "T_ROB1",
                "MainModule",
                "MODULE MainModule\nENDMODULE\n",
                expected_change_count=7,
            )
        self.assertEqual(calls, 1)
        self.assertTrue(change.changed)
        self.assertEqual(change.change_count_after, 8)

        with _client(handler) as client:
            with self.assertRaisesRegex(ConfigurationError, "concurrently"):
                RapidService(client).set_module_text(
                    "T_ROB1", "MainModule", "source", expected_change_count=6
                )

    def test_patches_source_range(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/changecount"):
                return httpx.Response(200, json={"state": [{"count": "20"}]})
            form = parse_qs(request.content.decode())
            self.assertEqual(form["replace-mode"], ["After"])
            self.assertEqual(form["startrow"], ["3"])
            self.assertEqual(form["text"], ["    ! comment\n"])
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "module-changed-name": "false",
                            "new-modnam": "",
                            "change-count": "21",
                        }
                    ]
                },
            )

        with _client(handler) as client:
            result = RapidService(client).set_text_range(
                "T_ROB1",
                "MainModule",
                replace_mode="After",
                start_row=3,
                start_column=1,
                end_row=3,
                end_column=10,
                text="    ! comment\n",
                expected_change_count=20,
            )
        self.assertEqual(result.change_count_after, 21)

    def test_module_lifecycle_build_and_diagnostics(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}")
            if request.url.path.endswith("/loadmod"):
                self.assertEqual(
                    parse_qs(request.content.decode())["replace"], ["true"]
                )
                return httpx.Response(
                    200,
                    json={
                        "state": [{"_type": "rap-task-module-li", "name": "NewModule"}]
                    },
                )
            if request.url.path.endswith("/builderror"):
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rap-builderrs",
                                "ModuleName": "NewModule",
                                "row": "4",
                                "column": "9",
                                "error-num": "135",
                                "error": "missing semicolon",
                            }
                        ]
                    },
                )
            return httpx.Response(204)

        with _client(handler) as client:
            service = RapidService(client)
            loaded = service.load_module("T_ROB1", "$TEMP/New.mod", replace=True)
            service.save_module("T_ROB1", "NewModule", path="$HOME", name="New")
            service.build_task("T_ROB1")
            errors = service.get_build_errors("T_ROB1")
            service.unload_module("T_ROB1", "NewModule")

        self.assertEqual(loaded.module, "NewModule")
        self.assertEqual(errors[0].error_number, "135")
        self.assertIn("POST /rw/rapid/tasks/T_ROB1/build", calls)

    def test_whole_program_operations(self) -> None:
        forms: list[tuple[str, dict[str, list[str]]]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "state": [
                            {
                                "_type": "rap-program",
                                "name": "Production",
                                "entrypoint": "main",
                            }
                        ]
                    },
                )
            forms.append((request.url.path, parse_qs(request.content.decode())))
            return httpx.Response(204)

        with _client(handler) as client:
            service = RapidService(client)
            program = service.get_program("T_ROB1")
            service.load_program("T_ROB1", "$HOME/app.pgf", replace=True)
            service.save_program("T_ROB1", "$HOME/saved")
            service.set_program_name("T_ROB1", "NewName")
            service.set_entry_point("T_ROB1", "main2")
            service.unload_program("T_ROB1")

        self.assertEqual(program.entry_point, "main")
        self.assertEqual(forms[0][1]["progpath"], ["$HOME/app.pgf"])
        self.assertEqual(forms[2][1]["name"], ["NewName"])


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
