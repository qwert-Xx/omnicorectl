from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from omnicorectl.rws import RwsClient
from omnicorectl.services.io import IoService


def signal(name: str, title: str) -> dict[str, str]:
    return {
        "_type": "ios-signal-li",
        "_title": title,
        "name": name,
        "type": "DI",
        "category": "internal",
        "lvalue": "1",
        "lstate": "not simulated",
    }


class IoSignalsTests(unittest.TestCase):
    def test_gets_every_page_without_filters(self) -> None:
        requested_starts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.method, "GET")
            requested_starts.append(request.url.params["start"])
            if request.url.params["start"] == "0":
                return httpx.Response(
                    200,
                    json={
                        "_links": {"next": {"href": "signals?start=2&amp;limit=2"}},
                        "_embedded": {
                            "resources": [
                                signal("DI_1", "EtherCAT/Device/DI_1"),
                                signal("DI_2", "EtherCAT/Device/DI_2"),
                            ]
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "_links": {},
                    "_embedded": {"resources": [signal("LooseSignal", "LooseSignal")]},
                },
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            signals = IoService(client).list_signals(page_size=2)

        self.assertEqual(requested_starts, ["0", "2"])
        self.assertEqual(
            [item.name for item in signals], ["DI_1", "DI_2", "LooseSignal"]
        )
        self.assertEqual(signals[0].network, "EtherCAT")
        self.assertEqual(signals[0].device, "Device")
        self.assertIsNone(signals[2].network)

    def test_uses_signal_search_post_for_filters(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/rw/iosystem/signals/signal-search")
            self.assertEqual(
                request.headers["content-type"],
                "application/x-www-form-urlencoded;v=2.0",
            )
            body = parse_qs(request.content.decode())
            self.assertEqual(body["network"], ["EtherCAT"])
            self.assertEqual(body["device"], ["EC_Internal_Device"])
            return httpx.Response(
                200, json={"_links": {}, "_embedded": {"resources": []}}
            )

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            signals = IoService(client).list_signals(
                network="EtherCAT", device="EC_Internal_Device"
            )

        self.assertEqual(signals, [])

    def test_gets_detailed_signal_state(self) -> None:
        payload = {
            "_embedded": {
                "resources": [
                    {
                        "_type": "ios-signal-li",
                        "_title": "Network/Device/Signal",
                        "name": "Signal",
                        "type": "DI",
                        "category": "internal",
                        "lvalue": "1",
                        "lstate": "not simulated",
                        "pvalue": "1",
                        "phstate": "valid",
                        "quality": "good",
                        "access-level": "Internal/Read-only",
                        "write-access": "None",
                        "safe-level": "N/A",
                    }
                ]
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            self.assertEqual(
                request.url.path, "/rw/iosystem/signals/Network/Device/Signal"
            )
            return httpx.Response(200, json=payload)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            details = IoService(client).get_signal("Network", "Device", "Signal")

        self.assertEqual(details.logical_value, "1")
        self.assertEqual(details.physical_state, "valid")
        self.assertEqual(details.quality, "good")
        self.assertEqual(details.write_access, "None")


if __name__ == "__main__":
    unittest.main()
