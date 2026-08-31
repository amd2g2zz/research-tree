"""Canonical claim, speech-act, and authority-transition model.

Unifies Living Brief / AlignmentGraph / Intent Model status vocabulary
through a single :class:`SpeechAct` + :func:`transition` table.  ``record_belief``
defaults to ``candidate`` when basis_refs is empty; only an ``acceptance`` speech-act
under ``decision_owner`` authority can promote a belief to ``resolved``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Sequence

SPEECH_ACT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "assert",
        "claim",
        "question",
        "correction",
        "acceptance",
        "rejection",
        "answered",
        "proposed",
    }
)
SPEAKER_ROLES: Final[frozenset[str]] = frozenset({"human", "agent", "operator"})
AUTHORITY_SCOPES: Final[frozenset[str]] = frozenset(
    {
        "intent_owner",
        "research_owner",
        "decision_owner",
        "approval_required",
        "authority_scope",
    }
)
BELIEF_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "candidate",
        "isolated",
        "corroborated",
        "rejected",
        "superseded",
        "contested",
        "unasserted",
        "resolved",
    }
)


class AuthorityTransitionError(ValueError):
    """Raised when a speech-act cannot drive a valid authority transition."""


@dataclass(frozen=True, slots=True)
class SpeechAct:
    """A canonical claim, with the speaker and authority that produced it.

    ``basis_refs`` is required to disambiguate ``assert``: an assertion with
    no basis is *unasserted*, not a candidate.  ``authority_scope`` decides
    whether ``acceptance`` actually closes a question (only ``decision_owner``
    or ``approval_required`` authority may resolve).
    """

    kind: str
    speaker_role: str
    speaker_id: str
    addressee: str
    authority_scope: str
    timestamp: str
    claim_id: str | None = None
    basis_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in SPEECH_ACT_KINDS:
            raise AuthorityTransitionError(
                f"unsupported speech-act kind: {self.kind!r}; allowed: {', '.join(sorted(SPEECH_ACT_KINDS))}"
            )
        if self.speaker_role not in SPEAKER_ROLES:
            raise AuthorityTransitionError(
                f"unsupported speaker_role: {self.speaker_role!r}; allowed: {', '.join(sorted(SPEAKER_ROLES))}"
            )
        if self.authority_scope not in AUTHORITY_SCOPES:
            raise AuthorityTransitionError(
                f"unsupported authority_scope: {self.authority_scope!r}; allowed: {', '.join(sorted(AUTHORITY_SCOPES))}"
            )
        for field in ("speaker_id", "addressee", "timestamp"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise AuthorityTransitionError(f"{field} must be a non-empty string")
        if self.claim_id is not None and not str(self.claim_id).strip():
            raise AuthorityTransitionError("claim_id must be a non-empty string when provided")
        object.__setattr__(self, "speaker_id", self.speaker_id.strip())
        object.__setattr__(self, "addressee", self.addressee.strip())
        object.__setattr__(self, "timestamp", self.timestamp.strip())
        basis = tuple(self.basis_refs)
        if len(set(basis)) != len(basis):
            raise AuthorityTransitionError("basis_refs must not contain duplicates")
        object.__setattr__(self, "basis_refs", basis)
        if self.claim_id is not None:
            object.__setattr__(self, "claim_id", self.claim_id.strip())

    @classmethod
    def for_assert(
        cls,
        *,
        basis_refs: Sequence[str] = (),
        speaker_role: str = "agent",
        speaker_id: str = "agent",
        addressee: str = "human",
        authority_scope: str = "research_owner",
        timestamp: str | None = None,
        claim_id: str | None = None,
    ) -> "SpeechAct":
        """Build an ``assert`` speech-act with a normalized UTC timestamp."""

        return cls(
            kind="assert",
            speaker_role=speaker_role,
            speaker_id=speaker_id,
            addressee=addressee,
            authority_scope=authority_scope,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            claim_id=claim_id,
            basis_refs=tuple(basis_refs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "speaker_role": self.speaker_role,
            "speaker_id": self.speaker_id,
            "addressee": self.addressee,
            "authority_scope": self.authority_scope,
            "timestamp": self.timestamp,
            "claim_id": self.claim_id,
            "basis_refs": list(self.basis_refs),
        }

    @classmethod
    def from_value(cls, value: "SpeechAct | Mapping[str, Any]") -> "SpeechAct":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise AuthorityTransitionError("speech-act must be a SpeechAct or mapping")
        return cls(
            kind=str(value.get("kind", "assert")),
            speaker_role=str(value.get("speaker_role", "agent")),
            speaker_id=str(value.get("speaker_id", "agent")),
            addressee=str(value.get("addressee", "human")),
            authority_scope=str(value.get("authority_scope", "research_owner")),
            timestamp=str(value.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            claim_id=value.get("claim_id"),
            basis_refs=tuple(value.get("basis_refs", ()) or ()),
        )


AuthorityTransition: Final[Mapping[str, frozenset[tuple[str, str]]]] = {
    "assert": frozenset(
        {
            ("candidate", "candidate"),
            ("candidate", "unasserted"),
            ("unasserted", "candidate"),
            ("isolated", "candidate"),
            ("corroborated", "corroborated"),
        }
    ),
    "claim": frozenset(
        {
            ("candidate", "candidate"),
            ("candidate", "corroborated"),
            ("isolated", "corroborated"),
            ("corroborated", "corroborated"),
        }
    ),
    "question": frozenset(
        {
            ("candidate", "candidate"),
            ("isolated", "candidate"),
            ("corroborated", "candidate"),
            ("resolved", "resolved"),
        }
    ),
    "correction": frozenset(
        {
            ("candidate", "candidate"),
            ("isolated", "candidate"),
            ("corroborated", "contested"),
            ("resolved", "contested"),
        }
    ),
    "acceptance": frozenset(
        {
            ("candidate", "resolved"),
            ("isolated", "resolved"),
            ("corroborated", "resolved"),
            ("contested", "resolved"),
        }
    ),
    "rejection": frozenset(
        {
            ("candidate", "rejected"),
            ("isolated", "rejected"),
            ("contested", "rejected"),
        }
    ),
    "answered": frozenset(
        {
            ("candidate", "candidate"),
            ("isolated", "candidate"),
            ("corroborated", "candidate"),
            ("unasserted", "unasserted"),
            ("contested", "candidate"),
        }
    ),
    "proposed": frozenset(
        {
            ("candidate", "candidate"),
            ("isolated", "candidate"),
        }
    ),
}


def transition(current: str, act: SpeechAct) -> str:
    """Apply ``act`` to ``current`` and return the next belief status.

    Raises :class:`AuthorityTransitionError` if ``act`` is not allowed from
    ``current``, or if the speech-act lacks the authority scope required by
    its kind (e.g. ``acceptance`` requires ``decision_owner``).
    """

    if current not in BELIEF_STATUSES:
        raise AuthorityTransitionError(f"unknown belief status: {current!r}")
    if act.kind not in AuthorityTransition:
        raise AuthorityTransitionError(f"unsupported speech-act kind: {act.kind!r}")
    if act.kind == "assert" and not act.basis_refs:
        return "unasserted"
    if act.kind == "assert" and act.basis_refs and current == "candidate":
        return current  # assertion with evidence on a candidate stays candidate
    if act.kind == "acceptance" and act.authority_scope not in {"decision_owner", "approval_required"}:
        raise AuthorityTransitionError("acceptance requires decision_owner or approval_required authority_scope")
    rules = AuthorityTransition[act.kind]
    for from_status, to_status in rules:
        if from_status == current:
            return to_status
    raise AuthorityTransitionError(f"speech-act {act.kind!r} cannot transition from {current!r}")


def normalize_status(status: Any) -> str:
    """Check ``status`` against the canonical vocabulary.

    Unrecognized statuses fall through as ``candidate`` so callers can keep
    consuming graph state without rejecting it.  A deprecation warning is
    emitted via :mod:`warnings` so consumers see the signal.
    """

    if isinstance(status, str) and status in BELIEF_STATUSES:
        return status
    import warnings

    warnings.warn(
        f"alignment-graph status {status!r} is unrecognized; defaulting to 'candidate'",
        DeprecationWarning,
        stacklevel=2,
    )
    return "candidate"


__all__ = [
    "AUTHORITY_SCOPES",
    "AuthorityTransition",
    "AuthorityTransitionError",
    "BELIEF_STATUSES",
    "SPEAKER_ROLES",
    "SPEECH_ACT_KINDS",
    "SpeechAct",
    "normalize_status",
    "transition",
]
