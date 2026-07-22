from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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

    def test_downloads_atomically_and_refuses_overwrite(self) -> None:
        content = b"binary\x00controller\xffdata"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(
                request.url.raw_path,
                b"/fileservice/%24HOME/Safety%20Configuration%20Report.pdf",
            )
            return httpx.Response(200, content=content)

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "report.pdf"
            with RwsClient(
                "192.0.2.1",
                "test-user",
                "test-password",
                transport=httpx.MockTransport(handler),
                request_interval=0,
            ) as client:
                service = FileService(client)
                result = service.download_file(
                    "$HOME/Safety Configuration Report.pdf", destination
                )
                self.assertEqual(destination.read_bytes(), content)
                self.assertEqual(result.bytes_written, len(content))
                with self.assertRaises(ConfigurationError):
                    service.download_file("$HOME/other.pdf", destination)

            self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_uploads_binary_file_after_remote_existence_check(self) -> None:
        content = b"upload\x00contents\xff"
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append(f"{request.method} {request.url.path}")
            if request.method == "GET":
                return httpx.Response(
                    200, json={"_embedded": {"resources": []}}
                )
            self.assertEqual(request.method, "PUT")
            self.assertEqual(
                request.url.raw_path, b"/fileservice/%24TEMP/test%20upload.bin"
            )
            self.assertEqual(
                request.headers["content-type"],
                "application/octet-stream;v=2.0",
            )
            self.assertEqual(int(request.headers["content-length"]), len(content))
            self.assertEqual(request.content, content)
            return httpx.Response(201)

        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(content)
            with RwsClient(
                "192.0.2.1",
                "test-user",
                "test-password",
                transport=httpx.MockTransport(handler),
                request_interval=0,
            ) as client:
                result = FileService(client).upload_file(
                    source, "$TEMP/test upload.bin"
                )

        self.assertEqual(result.bytes_written, len(content))
        self.assertEqual(result.remote_path, "/$TEMP/test upload.bin")
        self.assertEqual(
            calls,
            ["GET /fileservice/$TEMP", "PUT /fileservice/$TEMP/test upload.bin"],
        )


if __name__ == "__main__":
    unittest.main()
