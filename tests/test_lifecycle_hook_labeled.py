"""Tests for labeled lifecycle hook output (issue #440, tasks.md 3.1).

The hook's non-blocking host response must be wrapped in a balanced
``<rt:event>`` pair carrying the hook contract marker, so a host agent can
tell the injected content apart from its own reasoning.
"""

from __future__ import annotations

import re

from research_tree.lifecycle_hook import labeled_host_response

TAG_RE = re.compile(r"<rt:event ([^>]*)>")


def _attributes(raw: str) -> dict[str, str]:
    return dict(re.findall(r'(\w[\w-]*)="([^"]*)"', raw))


def test_labeled_host_response_rejects_unknown_host() -> None:
    import pytest

    from research_tree.lifecycle_hook import LifecycleHookError

    with pytest.raises(LifecycleHookError):
        labeled_host_response("unknown-host")
