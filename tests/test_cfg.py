from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.cfg import CfgService


class CfgTests(unittest.TestCase):
    def test_lists_only_cfg_domains(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {"_type": "cfg-domain-li", "_title": "EIO"},
                    {"_type": "future-resource", "_title": "ignore"},
                    {"_type": "cfg-domain-li", "_title": "MOC"},
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/cfg")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            domains = CfgService(client).list_domains()

        self.assertEqual([domain.name for domain in domains], ["EIO", "MOC"])


if __name__ == "__main__":
    unittest.main()
