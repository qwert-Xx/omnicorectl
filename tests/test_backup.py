from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.services.backup import BackupService


class BackupTests(unittest.TestCase):
    def test_reads_backup_state(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/ctrl/backup/state")
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "_type": "ctrl-backup-state",
                            "backup-state": "Backup Ready",
                        }
                    ]
                },
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            status = BackupService(client).status()

        self.assertEqual(status.state, "Backup Ready")

    def test_creates_archive_and_polls_until_ready(self) -> None:
        calls: list[str] = []
        poll_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal poll_count
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            calls.append(f"{request.method} {request.url.path}")
            if request.url.path == "/ctrl/backup/state":
                return httpx.Response(
                    200,
                    json={"state": [{"backup-state": "Backup Ready"}]},
                )
            if request.method == "GET" and request.url.path == "/fileservice/$TEMP":
                return httpx.Response(
                    200,
                    json={"_embedded": {"resources": []}},
                )
            if request.method == "POST":
                self.assertEqual(request.url.path, "/ctrl/backup/create")
                self.assertEqual(
                    dict(httpx.QueryParams(request.content.decode())),
                    {
                        "backup": "/fileservice/$TEMP/nightly",
                        "archive": "TRUE",
                    },
                )
                return httpx.Response(
                    202,
                    headers={"Location": "https://controller/progress/7"},
                )
            poll_count += 1
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "_type": "progress",
                            "_title": "backup",
                            "state": "pending" if poll_count == 1 else "ready",
                            "code": "294914" if poll_count == 1 else "294912",
                            "_links": {
                                "resource": {
                                    "href": "/fileservice/$TEMP/nightly"
                                }
                            },
                        }
                    ]
                },
            )

        sleeps: list[float] = []
        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            result = BackupService(
                client,
                clock=lambda: 10.0,
                sleep=sleeps.append,
            ).create("$TEMP/nightly", poll_interval=0.25)

        self.assertEqual(
            calls,
            [
                "GET /ctrl/backup/state",
                "GET /fileservice/$TEMP",
                "POST /ctrl/backup/create",
                "GET /progress/7",
                "GET /progress/7",
            ],
        )
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(result.progress_uri, "/progress/7")
        self.assertEqual(result.artifact_path, "/$TEMP/nightly.tar")
        self.assertEqual(result.resource_path, "/fileservice/$TEMP/nightly")
        self.assertEqual(result.code, "294912")

    def test_rejects_home_destination_before_request(self) -> None:
        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={})
            ),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ConfigurationError, "HOME"):
                BackupService(client).create("$HOME/not-allowed")

    def test_refuses_to_replace_existing_archive(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.url.path == "/ctrl/backup/state":
                return httpx.Response(
                    200,
                    json={"state": [{"backup-state": "Backup Ready"}]},
                )
            self.assertEqual(request.method, "GET")
            return httpx.Response(
                200,
                json={
                    "_embedded": {
                        "resources": [
                            {
                                "_type": "fs-file",
                                "_title": "nightly.tar",
                                "fs-size": "1024",
                                "fs-readonly": "false",
                                "fs-cdate": "created",
                                "fs-mdate": "modified",
                            }
                        ]
                    }
                },
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ConfigurationError, "already exists"):
                BackupService(client).create("$TEMP/nightly")

    def test_surfaces_terminal_backup_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.url.path == "/ctrl/backup/state":
                return httpx.Response(
                    200,
                    json={"state": [{"backup-state": "Backup Ready"}]},
                )
            if request.url.path == "/fileservice/$TEMP":
                return httpx.Response(
                    200,
                    json={"_embedded": {"resources": []}},
                )
            if request.method == "POST":
                return httpx.Response(202, headers={"Location": "/progress/8"})
            return httpx.Response(
                200,
                json={
                    "state": [
                        {
                            "state": "ready",
                            "code": "-1073445863",
                        }
                    ]
                },
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ProtocolError, "backup failed"):
                BackupService(client).create("$TEMP/failure")


if __name__ == "__main__":
    unittest.main()
