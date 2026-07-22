from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.rapid import RapidService


class RapidTasksTests(unittest.TestCase):
    def test_lists_only_task_resources(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {"_type": "rap-tasks-spy-li", "_title": "spy"},
                    {
                        "_type": "rap-task-li",
                        "name": "T_ROB1",
                        "type": "normal",
                        "taskstate": "loaded",
                        "excstate": "ready",
                        "active": "On",
                        "motiontask": "TRUE",
                    },
                    {
                        "_type": "rap-tasks-syncstate-pp-li",
                        "_title": "program-pointer",
                    },
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/rapid/tasks")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            tasks = RapidService(client).list_tasks()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "T_ROB1")
        self.assertEqual(tasks[0].execution_state, "ready")
        self.assertTrue(tasks[0].active)
        self.assertTrue(tasks[0].motion_task)

    def test_empty_embedded_list_is_a_valid_empty_result(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"_embedded": {"resources": []}})

        client = RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        )
        self.addCleanup(client.close)
        self.assertEqual(RapidService(client).list_tasks(), [])

    def test_lists_program_and_system_modules(self) -> None:
        payload = {
            "state": [
                {"_type": "rap-module-info-li", "name": "BASE", "type": "SysMod"},
                {
                    "_type": "rap-module-info-li",
                    "name": "EGM_StreamMotion",
                    "type": "ProgMod",
                },
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/rapid/tasks/T_ROB1/modules")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            modules = RapidService(client).list_modules("T_ROB1")

        self.assertEqual([module.name for module in modules], ["BASE", "EGM_StreamMotion"])
        self.assertEqual([module.module_type for module in modules], ["SysMod", "ProgMod"])

    def test_reads_module_source_without_changing_text(self) -> None:
        source_text = "MODULE TestModule\n    ! keep whitespace\nENDMODULE\n"
        payload = {
            "state": [
                {
                    "_type": "rap-module-text",
                    "change-count": " 421455 ",
                    "module-text": source_text,
                    "module-length": "52",
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(
                request.url.path,
                "/rw/rapid/tasks/T_ROB1/modules/TestModule/text",
            )
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            module = RapidService(client).get_module_source("T_ROB1", "TestModule")

        self.assertEqual(module.source, source_text)
        self.assertEqual(module.change_count, 421455)
        self.assertEqual(module.reported_length, 52)


if __name__ == "__main__":
    unittest.main()
