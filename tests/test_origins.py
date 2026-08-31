"""Tests for src/research_tree/origins.py (issue #440, tasks.md 1.1).

Pins the closed ORIGIN_TYPES vocabulary, the fail-closed require_origin
validator, and the balanced-XML tag helpers.
"""

from __future__ import annotations

import pytest

from research_tree.origins import (
    ORIGIN_TYPES,
    OriginError,
    close_tag,
    open_tag,
    require_origin,
)


class TestOriginVocabulary:
    def test_origin_types_exact_vocabulary(self) -> None:
        assert ORIGIN_TYPES == frozenset({"user", "agent", "worker", "tool", "repository", "generated"})

    def test_require_origin_accepts_known_values(self) -> None:
        for value in ("user", "agent", "worker", "tool", "repository", "generated"):
            assert require_origin(value, "origin") == value

    def test_require_origin_rejects_unknown_with_field_name(self) -> None:
        with pytest.raises(OriginError) as excinfo:
            require_origin("some-random-string", "origin")
        assert "origin" in str(excinfo.value)
        assert "some-random-string" in str(excinfo.value)

    def test_require_origin_rejects_non_string(self) -> None:
        with pytest.raises(OriginError) as excinfo:
            require_origin(None, "origin")
        assert "origin" in str(excinfo.value)

    def test_require_origin_rejects_empty(self) -> None:
        with pytest.raises(OriginError):
            require_origin("", "origin")

    def test_require_origin_rejects_whitespace_only(self) -> None:
        with pytest.raises(OriginError):
            require_origin("   ", "origin")


class TestTagHelpers:
    def test_open_tag_renders_attributes(self) -> None:
        rendered = open_tag("rt:tool-output", {"source": "research-tree-cli", "command": "status"})
        assert rendered == '<rt:tool-output source="research-tree-cli" command="status">'

    def test_close_tag_matches_open(self) -> None:
        assert close_tag("rt:tool-output") == "</rt:tool-output>"
        assert close_tag("rt:error") == "</rt:error>"

    def test_open_tag_escapes_attribute_values(self) -> None:
        rendered = open_tag("rt:tool-output", {"command": 'bad"quote&value'})
        # A raw double-quote immediately after command= would break the tag.
        assert rendered.startswith('<rt:tool-output command="bad')
        assert "&quot;" in rendered
        assert "&amp;" in rendered
        # No raw unescaped quote/ampersand inside the value.
        value_part = rendered[len('<rt:tool-output command="') : -len('">')]
        assert '"' not in value_part.replace("&quot;", "")
        import re

        assert not re.search(r"&(?!quot;|amp;|lt;|gt;|apos;|#)", value_part)

    def test_open_tag_with_no_attributes(self) -> None:
        rendered = open_tag("rt:digest", {})
        assert rendered == "<rt:digest>"

    def test_round_trip_balanced(self) -> None:
        opened = open_tag("rt:observation", {"origin": "worker"})
        closed = close_tag("rt:observation")
        payload = '{"evidence": "something"}'
        block = f"{opened}{payload}{closed}"
        assert block.startswith("<rt:observation ")
        assert block.endswith("</rt:observation>")
        assert payload in block
