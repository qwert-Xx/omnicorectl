from __future__ import annotations

import unittest

import httpx

from omnicorectl.errors import AuthorizationError, ProtocolError, RwsHttpError
from omnicorectl.rws import RwsClient


class RwsClientErrorTests(unittest.TestCase):
    def test_form_outcome_preserves_sync_and_async_completion(self) -> None:
        responses = iter(
            (
                httpx.Response(204),
                httpx.Response(
                    202,
                    headers={"Location": "https://controller/progress/17?view=full"},
                ),
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return next(responses)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            synchronous = client.post_form_outcome("/sync")
            asynchronous = client.post_form_outcome("/async")

        self.assertEqual(synchronous.status_code, 204)
        self.assertIsNone(synchronous.progress_uri)
        self.assertEqual(asynchronous.status_code, 202)
        self.assertEqual(asynchronous.progress_uri, "/progress/17?view=full")

    def test_async_form_requires_progress_location(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(202)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(ProtocolError, "no Location"):
                client.post_form_outcome("/async")

    def test_preserves_json_controller_error_code_and_message(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(
                400,
                json={
                    "status": {
                        "code": -20103,
                        "msg": "Control station id not allowed",
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
            with self.assertRaises(RwsHttpError) as raised:
                client.get_json("/test")

        error = raised.exception
        self.assertEqual(error.status_code, 400)
        self.assertEqual(error.controller_code, "-20103")
        self.assertEqual(error.controller_message, "Control station id not allowed")
        self.assertIn("ABB -20103", str(error))

    def test_includes_xhtml_detail_in_authorization_error(self) -> None:
        body = b"""\
        <html xmlns="http://www.w3.org/1999/xhtml"><body>
          <div class="status">
            <span class="code">-1073445863</span>
            <span class="msg">The request was denied.</span>
          </div>
        </body></html>
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/logout":
                return httpx.Response(200, json={})
            return httpx.Response(403, content=body)

        with RwsClient(
            "192.0.2.1",
            "test-user",
            "test-password",
            transport=httpx.MockTransport(handler),
            request_interval=0,
        ) as client:
            with self.assertRaisesRegex(
                AuthorizationError, "ABB -1073445863: The request was denied"
            ):
                client.get_json("/protected")


if __name__ == "__main__":
    unittest.main()
