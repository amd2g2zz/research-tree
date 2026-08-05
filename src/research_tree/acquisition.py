"""Typed acquisition results; failed acquisition remains auditable."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping

from .security import PermissionProfile


class AcquisitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    acquisition_id: str
    method_id: str
    locator: str
    status: str
    content_digest: str | None
    provenance_group: str
    limitation: str | None
    license_note: str | None
    redistributable: bool
    acquired_at: str
    next_action: str | None = None

    @classmethod
    def create(cls, *, acquisition_id: str, method_id: str, locator: str, status: str, provenance_group: str, content_digest: str | None = None, limitation: str | None = None, license_note: str | None = None, redistributable: bool = False, next_action: str | None = None, acquired_at: str | None = None) -> "AcquisitionResult":
        if status not in {"acquired", "empty", "blocked", "unparsed", "failed", "unavailable"}:
            raise AcquisitionError("unsupported acquisition status")
        if not all(isinstance(value, str) and value.strip() for value in (acquisition_id, method_id, locator, provenance_group)):
            raise AcquisitionError("acquisition identity fields must be nonempty")
        if status != "acquired" and not limitation:
            raise AcquisitionError("failed acquisition requires a limitation")
        if not isinstance(redistributable, bool):
            raise AcquisitionError("redistributable must be boolean")
        return cls(acquisition_id, method_id, locator, status, content_digest, provenance_group, limitation, license_note, redistributable, acquired_at or datetime.now(timezone.utc).isoformat(), next_action)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_failure(*, acquisition_id: str, method_id: str, locator: str, reason: str, provenance_group: str, next_action: str) -> AcquisitionResult:
    return AcquisitionResult.create(acquisition_id=acquisition_id, method_id=method_id, locator=locator, status="failed", provenance_group=provenance_group, limitation=reason, next_action=next_action)


def authorize_acquisition(profile: PermissionProfile, *, needs_network: bool) -> None:
    if needs_network and profile.network == "none":
        raise AcquisitionError("network acquisition is outside permission profile")
