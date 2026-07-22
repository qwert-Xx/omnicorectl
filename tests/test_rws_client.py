from __future__ import annotations

import unittest

import httpx

from omnicorectl.errors import AuthorizationError, RwsHttpError
from omnicorectl.rws import RwsClient


class RwsClientErrorTests(unittest.TestCase):
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
