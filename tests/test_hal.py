from __future__ import annotations

import unittest

from omnicorectl.errors import ProtocolError
from omnicorectl.rws.hal import (
    first_state,
    has_next_link,
    required_int,
    required_text,
    state_resources,
)


class HalParserTests(unittest.TestCase):
    def test_first_state_accepts_additive_fields(self) -> None:
        state = first_state(
            {"state": [{"name": "robot", "new-in-rw9": 42}]}, resource="test"
        )
        self.assertEqual(state["name"], "robot")

    def test_first_state_rejects_missing_collection(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "state is not a list"):
            first_state({}, resource="test")

    def test_required_text_rejects_empty_value(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "missing text field"):
            required_text({"name": ""}, "name", resource="test")

    def test_state_resources_allows_empty_list(self) -> None:
        self.assertEqual(state_resources({"state": []}, resource="test"), [])

    def test_required_int_strips_controller_whitespace(self) -> None:
        self.assertEqual(required_int({"count": " 421455 "}, "count", resource="test"), 421455)

    def test_has_next_link_validates_hal_shape(self) -> None:
        self.assertTrue(
            has_next_link(
                {"_links": {"next": {"href": "signals?start=10&amp;limit=10"}}},
                resource="test",
            )
        )
        self.assertFalse(has_next_link({"_links": {}}, resource="test"))


if __name__ == "__main__":
    unittest.main()
