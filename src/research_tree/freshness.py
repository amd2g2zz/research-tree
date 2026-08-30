"""Operational freshness policy for repository baselines (issue #327).

Distinct from revision integrity (already enforced by intake/source_capture):
this module decides whether an inspected baseline is current enough for the
intended use.  A stale baseline that touches implementation-relevant paths
forces revalidation or an explicit historical-analysis disposition; offline
or unreachable authority becomes freshness_unknown — never silently current,
never globally blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class FreshnessError(ValueError):
    """Raised when a freshness policy or assessment payload is malformed."""


FRESHNESS_DISPOSITIONS = frozenset(
    {
        "current",
        "stale_relevant",
        "stale_irrelevant",
        "freshness_unknown",
        "historical_analysis_authorized",
    }
)


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Authorized remote/ref, allowed divergence, implementation-relevant paths."""

    authorized_remote: str | None = None
    authorized_ref: str | None = None
    allowed_ahead: int = 10
    allowed_behind: int = 10
    relevant_paths: tuple[str, ...] = ()
    allow_historical_analysis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized_remote": self.authorized_remote,
            "authorized_ref": self.authorized_ref,
            "allowed_ahead": self.allowed_ahead,
            "allowed_behind": self.allowed_behind,
            "relevant_paths": list(self.relevant_paths),
            "allow_historical_analysis": self.allow_historical_analysis,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FreshnessPolicy":
        if not isinstance(value, Mapping):
            raise FreshnessError("freshness policy must be a mapping")
        allowed_ahead = value.get("allowed_ahead", 0)
        allowed_behind = value.get("allowed_behind", 0)
        for label, n in (("allowed_ahead", allowed_ahead), ("allowed_behind", allowed_behind)):
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise FreshnessError(f"{label} must be a non-negative integer")
        relevant_paths = value.get("relevant_paths", ())
        if not isinstance(relevant_paths, Iterable) or isinstance(relevant_paths, (str, bytes)):
            raise FreshnessError("relevant_paths must be an iterable of strings")
        relevant = tuple(str(item) for item in relevant_paths)
        return cls(
            authorized_remote=value.get("authorized_remote"),
            authorized_ref=value.get("authorized_ref"),
            allowed_ahead=allowed_ahead,
            allowed_behind=allowed_behind,
            relevant_paths=relevant,
            allow_historical_analysis=bool(value.get("allow_historical_analysis", False)),
        )


@dataclass(frozen=True, slots=True)
class BaselineFreshness:
    """The admission record for one repository baseline's freshness."""

    inspected_commit: str
    authority_commit: str | None
    observed_at: str
    ahead: int
    behind: int
    relevant_path_changes: tuple[str, ...]
    policy: FreshnessPolicy
    disposition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspected_commit": self.inspected_commit,
            "authority_commit": self.authority_commit,
            "observed_at": self.observed_at,
            "ahead": self.ahead,
            "behind": self.behind,
            "relevant_path_changes": list(self.relevant_path_changes),
            "policy": self.policy.to_dict(),
            "disposition": self.disposition,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_overlaps(changed: Iterable[str], relevant: Iterable[str]) -> tuple[str, ...]:
    """Prefix-overlap: a changed path "src/coordinator.py" matches relevant "src/".

    Exact equality is a special case of prefix overlap (empty prefix matches
    nothing; a path that starts with "/" needs a relevant prefix to anchor it).
    """

    matches: set[str] = set()
    for changed_path in (str(path) for path in changed):
        for relevant_path in (str(path) for path in relevant):
            if relevant_path and changed_path == relevant_path:
                matches.add(changed_path)
                break
            if relevant_path and changed_path.startswith(relevant_path):
                matches.add(changed_path)
                break
    return tuple(sorted(matches))


def assess(
    *,
    inspected_commit: str,
    authority_commit: str | None,
    ahead: int,
    behind: int | None,
    changed_paths: Iterable[str],
    policy: FreshnessPolicy,
    historical_analysis_authorized: bool = False,
) -> BaselineFreshness:
    """Pure decision: pure function returning the admission record."""

    if not isinstance(inspected_commit, str) or not inspected_commit:
        raise FreshnessError("inspected_commit must be a non-empty string")
    if authority_commit is not None and not isinstance(authority_commit, str):
        raise FreshnessError("authority_commit must be a string or None")
    if not isinstance(ahead, int) or isinstance(ahead, bool) or ahead < 0:
        raise FreshnessError("ahead must be a non-negative integer")
    if behind is not None and (not isinstance(behind, int) or isinstance(behind, bool) or behind < 0):
        raise FreshnessError("behind must be a non-negative integer or None")

    changed = tuple(str(path) for path in changed_paths)
    overlaps = _path_overlaps(changed, policy.relevant_paths)

    if authority_commit is None:
        disposition = "freshness_unknown"
    elif historical_analysis_authorized and policy.allow_historical_analysis:
        disposition = "historical_analysis_authorized"
    elif ahead > policy.allowed_ahead or (behind is not None and behind > policy.allowed_behind):
        disposition = "stale_relevant" if overlaps else "stale_irrelevant"
    elif overlaps:
        disposition = "stale_relevant"
    else:
        disposition = "current"

    if disposition not in FRESHNESS_DISPOSITIONS:
        raise FreshnessError(f"unknown freshness disposition: {disposition}")

    return BaselineFreshness(
        inspected_commit=inspected_commit,
        authority_commit=authority_commit,
        observed_at=_utc_now_iso(),
        ahead=ahead,
        behind=behind if behind is not None else 0,
        relevant_path_changes=overlaps,
        policy=policy,
        disposition=disposition,
    )
