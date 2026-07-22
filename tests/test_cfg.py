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

    def test_lists_types_in_domain(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {"_type": "cfg-dt-li", "_title": "EIO_SIGNAL"},
                    {"_type": "cfg-dt-li", "_title": "ETHERCAT_NETWORK"},
                    {"_type": "future-resource", "_title": "ignore"},
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/cfg/EIO")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            cfg_types = CfgService(client).list_types("EIO")

        self.assertEqual(
            [cfg_type.name for cfg_type in cfg_types],
            ["EIO_SIGNAL", "ETHERCAT_NETWORK"],
        )
        self.assertTrue(all(cfg_type.domain == "EIO" for cfg_type in cfg_types))

    def test_lists_all_instance_pages_and_preserves_empty_attributes(self) -> None:
        def instance(name: str, instance_id: str) -> dict[str, object]:
            return {
                "_type": "cfg-dt-instance-li",
                "_title": name,
                "rdonly": "false",
                "instanceid": instance_id,
                "attrib": [
                    {"_type": "cfg-ia-t", "_title": "Name", "value": name},
                    {"_type": "cfg-ia-t", "_title": "Label", "value": ""},
                ],
            }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/cfg/EIO/EIO_SIGNAL/instances")
            if request.url.params["start"] == "0":
                return httpx.Response(
                    200,
                    json={
                        "_links": {"next": {"href": "ignored-escaped-link"}},
                        "_embedded": {"resources": [instance("Signal1", "10")]},
                    },
                )
            self.assertEqual(request.url.params["start"], "1")
            return httpx.Response(
                200,
                json={
                    "_links": {},
                    "_embedded": {"resources": [instance("Signal2", "11")]},
                },
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            instances = CfgService(client).list_instances(
                "EIO", "EIO_SIGNAL", page_size=1
            )

        self.assertEqual([item.name for item in instances], ["Signal1", "Signal2"])
        self.assertEqual(instances[0].attributes["Label"], "")
        self.assertFalse(instances[0].read_only)


if __name__ == "__main__":
    unittest.main()
