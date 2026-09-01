"""Tests for labeled lifecycle hook output (issue #440, tasks.md 3.1).

The hook's non-blocking host response must be wrapped in a balanced
``<rt:event>`` pair carrying the hook contract marker, so a host agent can
tell the injected content apart from its own reasoning.
"""

from __future__ import annotations

import re

from research_tree.lifecycle_hook import host_response, labeled_host_response

TAG_RE = re.compile(r"<rt:event ([^>]*)>")


def _attributes(raw: str) -> dict[str, str]:
    return dict(re.findall(r'(\w[\w-]*)="([^"]*)"', raw))


def test_labeled_host_response_is_balanced_rt_event_pair() -> None:
    for host in ("codex", "claude", "hermes"):
        labeled = labeled_host_response(host)
        open_match = TAG_RE.search(labeled)
        assert open_match, (host, labeled)
        assert labeled.endswith("</rt:event>")
        attrs = _attributes(open_match.group(1))
        assert attrs["contract"] == "research-tree-hook"
        assert attrs["schema_version"]
        assert attrs["host"] == host


def test_labeled_host_response_inner_matches_host_response() -> None:
    import json

    for host in ("codex", "hermes"):
        labeled = labeled_host_response(host)
        inner = labeled[labeled.index(">") + 1 : -len("</rt:event>")]
        assert json.loads(inner) == host_response(host)


def test_labeled_host_response_rejects_unknown_host() -> None:
    import pytest

    from research_tree.lifecycle_hook import LifecycleHookError

    with pytest.raises(LifecycleHookError):
        labeled_host_response("unknown-host")
