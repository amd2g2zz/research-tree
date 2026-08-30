"""Authority roles for Problem Forest nodes (issue #314).

Authority is explicit per node: every forest node carries exactly one role,
and consumers route responsibilities through `role_of` / `authority_scope`.
"""

from __future__ import annotations

from enum import Enum


class AuthorityRole(Enum):
    """Who owns the truth or decision for this forest node."""

    INTENT_OWNER = "intent_owner"
    RESEARCH_OWNER = "research_owner"
    DECISION_OWNER = "decision_owner"
    APPROVAL_REQUIRED = "approval_required"
    AUTHORITY_SCOPE = "authority_scope"


def role_of(node: object) -> AuthorityRole:
    """Return the explicit authority role carried by a forest node.

    Raises ``TypeError`` when the value is not a forest node with `origin_role`.
    """

    role = getattr(node, "origin_role", None)
    if not isinstance(role, AuthorityRole):
        raise TypeError(f"node {node!r} has no explicit AuthorityRole")
    return role


def authority_scope(node: object) -> frozenset[str]:
    """Return the authority scope tags derived from a node's role.

    Each role maps to a single scope tag matching its enum value, so downstream
    consumers can gate side effects without depending on role ordering.
    """

    return frozenset({role_of(node).value})
