"""Closed origin vocabulary and balanced XML tag helpers (issue #440).

Every research-tree output that enters an agent's context is wrapped in a
balanced open/close XML tag identifying its source, so a consuming agent can
mechanically separate external tool output from its own generated content.
"""

from __future__ import annotations

from html import escape
from typing import Mapping

ORIGIN_TYPES = frozenset({"user", "agent", "worker", "tool", "repository", "generated"})


class OriginError(ValueError):
    """Raised when an origin label is missing, malformed, or unknown."""


def require_origin(value: object, label: str) -> str:
    """Return ``value`` if it is a member of ORIGIN_TYPES; raise otherwise."""

    if not isinstance(value, str) or not value.strip():
        raise OriginError(f"{label} must be a non-empty string drawn from ORIGIN_TYPES")
    if value not in ORIGIN_TYPES:
        raise OriginError(f"{label} must be one of {sorted(ORIGIN_TYPES)}; got {value!r}")
    return value


def open_tag(name: str, attributes: Mapping[str, str] | None = None) -> str:
    """Render an opening XML tag with escaped attribute values."""

    if not attributes:
        return f"<{name}>"
    rendered = " ".join(f'{key}="{escape(str(value), quote=True)}"' for key, value in attributes.items())
    return f"<{name} {rendered}>"


def close_tag(name: str) -> str:
    """Render the closing tag matching :func:`open_tag`."""

    return f"</{name}>"
