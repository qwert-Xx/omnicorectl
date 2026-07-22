from __future__ import annotations

import unittest

from omnicorectl.errors import ProtocolError
from omnicorectl.rws.hal import first_state, required_text


class HalParserTests(unittest.TestCase):
    def test_first_state_accepts_additive_fields(self) -> None:
        state = first_state(
            {"state": [{"name": "robot", "new-in-rw9": 42}]}, resource="test"
        )
        self.assertEqual(state["name"], "robot")

    def test_first_state_rejects_missing_collection(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "no state resource"):
            first_state({}, resource="test")

    def test_required_text_rejects_empty_value(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "missing text field"):
            required_text({"name": ""}, "name", resource="test")


if __name__ == "__main__":
    unittest.main()

