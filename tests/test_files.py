from __future__ import annotations

import unittest

import httpx

from omnicorectl.errors import ConfigurationError
from omnicorectl.rws import RwsClient
from omnicorectl.services.files import FileService


class FileServiceTests(unittest.TestCase):
    def test_lists_files_and_directories(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {
                        "_type": "fs-file",
                        "_title": "Dashboard.xml",
                        "fs-size": "6349",
                        "fs-readonly": "false",
                        "fs-cdate": "2026-07-17 T 19:25:52",
                        "fs-mdate": "2026-07-22 T 13:49:26",
                    },
                    {
                        "_type": "fs-dir",
                        "_title": "Code",
                        "fs-readonly": "false",
                        "fs-cdate": "2026-07-20 T 13:52:26",
                        "fs-mdate": "2026-07-22 T 16:27:54",
                    },
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.raw_path, b"/fileservice/%24HOME")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            entries = FileService(client).list_directory("/$HOME")

        self.assertEqual(entries[0].path, "/$HOME/Dashboard.xml")
        self.assertEqual(entries[0].size, 6349)
        self.assertFalse(entries[0].is_directory)
        self.assertEqual(entries[1].path, "/$HOME/Code")
        self.assertIsNone(entries[1].size)
        self.assertTrue(entries[1].is_directory)

    def test_rejects_parent_path_segments(self) -> None:
        client = object()
        service = FileService(client)  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            service.list_directory("/$HOME/../TEMP")


if __name__ == "__main__":
    unittest.main()
