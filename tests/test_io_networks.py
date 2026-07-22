from __future__ import annotations

import unittest

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.io import IoService


class IoNetworksTests(unittest.TestCase):
    def test_lists_only_network_resources(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {
                        "_type": "ios-network-li",
                        "name": "EtherCAT",
                        "pstate": "running",
                        "lstate": "started",
                    },
                    {"_type": "future-ios-resource", "name": "ignore-me"},
                    {
                        "_type": "ios-network-li",
                        "name": "Virtual",
                        "pstate": "running",
                        "lstate": "started",
                    },
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/iosystem/networks")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            networks = IoService(client).list_networks()

        self.assertEqual(
            [network.name for network in networks], ["EtherCAT", "Virtual"]
        )
        self.assertEqual(networks[0].physical_state, "running")
        self.assertEqual(networks[0].logical_state, "started")

    def test_lists_devices_with_network_query_parameter(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {
                        "_type": "ios-device-li",
                        "name": "EC_Internal_Device",
                        "pstate": "running",
                        "lstate": "enabled",
                        "address": "",
                    }
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.url.path, "/rw/iosystem/devices")
            self.assertEqual(request.url.params["network"], "EtherCAT")
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            devices = IoService(client).list_devices("EtherCAT")

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].network, "EtherCAT")
        self.assertEqual(devices[0].name, "EC_Internal_Device")
        self.assertEqual(devices[0].address, "")


if __name__ == "__main__":
    unittest.main()
