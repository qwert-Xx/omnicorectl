from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.errors import ProtocolError
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

    def test_gets_one_instance_with_numeric_instance_id(self) -> None:
        payload = {
            "state": [
                {
                    "_type": "cfg-dt-instance",
                    "_title": "EC_Internal_Device",
                    "rdonly": "false",
                    "instanceid": 6655648,
                    "attrib": [
                        {
                            "_type": "cfg-ia-t",
                            "_title": "OutputSize",
                            "value": "64",
                        }
                    ],
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(
                request.url.path,
                "/rw/cfg/EIO/ETHERCAT_INTERNAL_DEVICE/instances/EC_Internal_Device",
            )
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            instance = CfgService(client).get_instance(
                "EIO", "ETHERCAT_INTERNAL_DEVICE", "EC_Internal_Device"
            )

        self.assertEqual(instance.instance_id, "6655648")
        self.assertEqual(instance.attributes, {"OutputSize": "64"})

    def test_updates_validates_and_verifies_attribute(self) -> None:
        calls: list[tuple[str, str, str]] = []
        get_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal get_count
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            body = request.content.decode()
            calls.append((request.method, request.url.path, body))
            if request.method == "GET":
                get_count += 1
                return httpx.Response(
                    200,
                    json=_cfg_instance_payload(
                        "Signal1", "old" if get_count == 1 else "new"
                    ),
                )
            if request.url.path == "/rw/cfg/validate-instances":
                return httpx.Response(204)
            return httpx.Response(204)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            change = CfgService(client).set_attribute(
                "EIO", "EIO_SIGNAL", "Signal1", "Label", "new"
            )

        self.assertTrue(change.changed)
        self.assertTrue(change.validated)
        self.assertTrue(change.restart_required)
        self.assertEqual(change.old_value, "old")
        self.assertEqual(change.new_value, "new")
        self.assertEqual(
            calls,
            [
                (
                    "GET",
                    "/rw/cfg/EIO/EIO_SIGNAL/instances/Signal1",
                    "",
                ),
                (
                    "POST",
                    "/rw/cfg/EIO/EIO_SIGNAL/instances/Signal1",
                    "Label=%5Bnew%2C1%5D",
                ),
                (
                    "POST",
                    "/rw/cfg/validate-instances",
                    "operation=0&cfgdomain=EIO&cfgtype=EIO_SIGNAL&instances=%5BSignal1%5D",
                ),
                (
                    "GET",
                    "/rw/cfg/EIO/EIO_SIGNAL/instances/Signal1",
                    "",
                ),
            ],
        )

    def test_restores_original_value_after_validation_failure(self) -> None:
        posts: list[tuple[str, str]] = []
        validation_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal validation_count
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            if request.method == "GET":
                return httpx.Response(200, json=_cfg_instance_payload("Signal1", "old"))
            posts.append((request.url.path, request.content.decode()))
            if request.url.path == "/rw/cfg/validate-instances":
                validation_count += 1
                if validation_count == 1:
                    return httpx.Response(
                        200,
                        json={
                            "status": {
                                "valid": "false",
                                "code": "-1073437688",
                                "msg": "Cfg instance validation failed",
                            }
                        },
                    )
                return httpx.Response(204)
            return httpx.Response(204)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ProtocolError, "original value was restored"):
                CfgService(client).set_attribute(
                    "EIO", "EIO_SIGNAL", "Signal1", "Label", "bad"
                )

        self.assertEqual(
            [body for path, body in posts if path.endswith("/Signal1")],
            ["Label=%5Bbad%2C1%5D", "Label=%5Bold%2C1%5D"],
        )
        self.assertEqual(validation_count, 2)


def _cfg_instance_payload(name: str, label: str) -> dict[str, object]:
    return {
        "state": [
            {
                "_type": "cfg-dt-instance",
                "_title": name,
                "rdonly": "false",
                "instanceid": "10",
                "attrib": [
                    {"_type": "cfg-ia-t", "_title": "Name", "value": name},
                    {"_type": "cfg-ia-t", "_title": "Label", "value": label},
                ],
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
