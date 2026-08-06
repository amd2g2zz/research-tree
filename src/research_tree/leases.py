"""Renewable, replay-safe attempt leases.

Leases are data, not timers.  The coordinator persists the returned value and
uses ``expire`` during a scheduler tick; this keeps recovery deterministic and
does not depend on a background thread being alive.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping


class LeaseError(ValueError):
    pass


_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = frozenset({"leased", "running", "submitted", "verified", "retryable", "unknown", "rejected", "cancelled", "completed"})
_ACTIVE = frozenset({"leased", "running"})


def _utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LeaseError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LeaseError(f"{label} must be UTC")
    return parsed.astimezone(timezone.utc)


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LeaseError(f"{label} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class AttemptLease:
    attempt_id: str
    work_item_id: str
    run_id: str
    owner: str
    status: str
    dispatch_digest: str
    retry_ordinal: int
    started_at: str
    lease_expires_at: str
    heartbeat_sequence: int
    last_seen_at: str | None = None

    @classmethod
    def create(cls, *, attempt_id: str, work_item_id: str, run_id: str, owner: str,
               dispatch_digest: str, started_at: str, lease_expires_at: str,
               retry_ordinal: int = 0, heartbeat_sequence: int = 0,
               status: str = "leased", last_seen_at: str | None = None) -> "AttemptLease":
        for value, label in ((attempt_id, "attempt_id"), (work_item_id, "work_item_id"), (run_id, "run_id")):
            _id(value, label)
        if not isinstance(owner, str) or not owner.strip():
            raise LeaseError("owner must be nonempty")
        if not isinstance(dispatch_digest, str) or not _DIGEST.fullmatch(dispatch_digest):
            raise LeaseError("dispatch_digest must be lowercase SHA-256")
        if status not in _STATUSES:
            raise LeaseError("unsupported lease status")
        if not isinstance(retry_ordinal, int) or retry_ordinal < 0:
            raise LeaseError("retry_ordinal must be nonnegative")
        if not isinstance(heartbeat_sequence, int) or heartbeat_sequence < 0:
            raise LeaseError("heartbeat_sequence must be nonnegative")
        start = _utc(started_at, "started_at")
        expiry = _utc(lease_expires_at, "lease_expires_at")
        if expiry < start:
            raise LeaseError("lease_expires_at precedes started_at")
        if last_seen_at is not None:
            _utc(last_seen_at, "last_seen_at")
        return cls(attempt_id, work_item_id, run_id, owner, status, dispatch_digest,
                   retry_ordinal, start.isoformat(), expiry.isoformat(), heartbeat_sequence, last_seen_at)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AttemptLease":
        required = {"attempt_id", "work_item_id", "run_id", "owner", "status", "dispatch_digest", "retry_ordinal", "started_at", "lease_expires_at", "heartbeat_sequence"}
        optional = {"last_seen_at"}
        if set(value) - required - optional or required - set(value):
            raise LeaseError("attempt lease fields mismatch")
        return cls.create(**dict(value))

    def to_dict(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id, "work_item_id": self.work_item_id,
                "run_id": self.run_id, "owner": self.owner, "status": self.status,
                "dispatch_digest": self.dispatch_digest, "retry_ordinal": self.retry_ordinal,
                "started_at": self.started_at, "lease_expires_at": self.lease_expires_at,
                "heartbeat_sequence": self.heartbeat_sequence, "last_seen_at": self.last_seen_at}

    def expired(self, *, now: str | None = None) -> bool:
        instant = _utc(now, "now") if now else datetime.now(timezone.utc)
        return self.status in _ACTIVE and instant >= _utc(self.lease_expires_at, "lease_expires_at")

    def heartbeat(self, *, now: str, lease_seconds: int | None = None) -> "AttemptLease":
        if self.status not in _ACTIVE:
            raise LeaseError("only active leases can heartbeat")
        instant = _utc(now, "now")
        expiry = _utc(self.lease_expires_at, "lease_expires_at")
        if instant >= expiry:
            return replace(self, status="unknown", last_seen_at=instant.isoformat())
        if lease_seconds is not None:
            if not isinstance(lease_seconds, int) or lease_seconds <= 0:
                raise LeaseError("lease_seconds must be positive")
            expiry = instant + timedelta(seconds=lease_seconds)
        return replace(self, status="running", heartbeat_sequence=self.heartbeat_sequence + 1,
                       lease_expires_at=expiry.isoformat(), last_seen_at=instant.isoformat())

    def expire(self, *, now: str) -> "AttemptLease":
        return replace(self, status="unknown", last_seen_at=_utc(now, "now").isoformat()) if self.expired(now=now) else self

    def retry(self, *, dispatch_digest: str) -> "AttemptLease":
        if self.status not in {"retryable", "unknown"}:
            raise LeaseError("only retryable or unknown attempts can retry")
        return replace(self, attempt_id=f"{self.work_item_id}-retry-{self.retry_ordinal + 1}",
                       dispatch_digest=dispatch_digest, retry_ordinal=self.retry_ordinal + 1,
                       status="leased", heartbeat_sequence=0, last_seen_at=None)
