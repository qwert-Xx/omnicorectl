from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
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


if __name__ == "__main__":
    unittest.main()
