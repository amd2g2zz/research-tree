"""Inspectable project-local preference observations and hysteretic profiles."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from .domain import DataIntegrityError, canonical_json_bytes, thaw_json, validate_identifier
from .run_ledger import RunLedger

PREFERENCE_OBSERVATION_KIND = "preference-observation"
USER_PREFERENCE_PROFILE_KIND = "user-preference-profile"
PREFERENCE_SCHEMA_VERSION = 1
_BLOCKED_KEY_PARTS = frozenset({"demographic", "psychological", "personality", "medical", "secret", "credential"})
_OBSERVATION_FIELDS = {
    "schema_version",
    "kind",
    "observation_id",
    "project_id",
    "turn_number",
    "key",
    "value",
    "basis",
    "source_ref",
    "privacy",
    "reversal_condition",
    "supersedes_observation_id",
    "content_hash",
}


class PreferenceValidationError(DataIntegrityError):
    """Raised when preference state violates scope, privacy, or lineage rules."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PreferenceValidationError(f"{label} must be non-empty")
    return value.strip()


def _hash(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class PreferenceObservation:
    observation_id: str
    project_id: str
    turn_number: int
    key: str
    value: str
    basis: str
    source_ref: str
    privacy: str
    reversal_condition: str
    supersedes_observation_id: str | None
    content_hash: str

    @classmethod
    def create(cls, **values: Any) -> "PreferenceObservation":
        values = dict(values)
        supplied_hash = values.pop("content_hash", None)
        values.pop("schema_version", None)
        values.pop("kind", None)
        expected = {
            "observation_id",
            "project_id",
            "turn_number",
            "key",
            "value",
            "basis",
            "source_ref",
            "privacy",
            "reversal_condition",
            "supersedes_observation_id",
        }
        if set(values) != expected:
            raise PreferenceValidationError("observation fields do not match schema")
        try:
            observation_id = validate_identifier(values["observation_id"], "observation_id")
            project_id = validate_identifier(values["project_id"], "project_id")
        except DataIntegrityError as error:
            raise PreferenceValidationError(str(error)) from error
        turn_number = values["turn_number"]
        if isinstance(turn_number, bool) or not isinstance(turn_number, int) or turn_number < 1:
            raise PreferenceValidationError("turn_number must be positive")
        key = _text(values["key"], "key")
        if any(part.lower() in _BLOCKED_KEY_PARTS for part in key.replace("-", ".").split(".")):
            raise PreferenceValidationError("sensitive preference key is prohibited")
        basis = values["basis"]
        if basis not in {"explicit", "inferred"}:
            raise PreferenceValidationError("basis must be explicit or inferred")
        if values["privacy"] != "project-local":
            raise PreferenceValidationError("privacy must be project-local")
        supersedes = values["supersedes_observation_id"]
        if supersedes is not None:
            try:
                supersedes = validate_identifier(supersedes, "supersedes_observation_id")
            except DataIntegrityError as error:
                raise PreferenceValidationError(str(error)) from error
            if supersedes == observation_id:
                raise PreferenceValidationError("observation cannot supersede itself")
        normalized = {
            "schema_version": PREFERENCE_SCHEMA_VERSION,
            "kind": PREFERENCE_OBSERVATION_KIND,
            "observation_id": observation_id,
            "project_id": project_id,
            "turn_number": turn_number,
            "key": key,
            "value": _text(values["value"], "value"),
            "basis": basis,
            "source_ref": _text(values["source_ref"], "source_ref"),
            "privacy": "project-local",
            "reversal_condition": _text(values["reversal_condition"], "reversal_condition"),
            "supersedes_observation_id": supersedes,
        }
        content_hash = _hash(normalized)
        if supplied_hash is not None and supplied_hash != content_hash:
            raise PreferenceValidationError("observation digest mismatch")
        return cls(
            **{key: normalized[key] for key in normalized if key not in {"schema_version", "kind"}},
            content_hash=content_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREFERENCE_SCHEMA_VERSION,
            "kind": PREFERENCE_OBSERVATION_KIND,
            "observation_id": self.observation_id,
            "project_id": self.project_id,
            "turn_number": self.turn_number,
            "key": self.key,
            "value": self.value,
            "basis": self.basis,
            "source_ref": self.source_ref,
            "privacy": self.privacy,
            "reversal_condition": self.reversal_condition,
            "supersedes_observation_id": self.supersedes_observation_id,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PreferenceObservation":
        if not isinstance(value, Mapping) or set(value) != _OBSERVATION_FIELDS:
            raise PreferenceValidationError("observation fields do not match schema")
        if value.get("schema_version") != PREFERENCE_SCHEMA_VERSION or value.get("kind") != PREFERENCE_OBSERVATION_KIND:
            raise PreferenceValidationError("observation schema identity is invalid")
        return cls.create(**thaw_json(value))


@dataclass(frozen=True, slots=True)
class PreferenceEntry:
    key: str
    value: str
    status: str
    precedence: str
    source_observation_ids: tuple[str, ...]
    reversal_condition: str
    shadow_value: str | None = None
    shadow_observation_ids: tuple[str, ...] = ()
    shadow_refreshes: int = 0
    last_supported_refresh: int = 0
    lineage: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "status": self.status,
            "precedence": self.precedence,
            "source_observation_ids": list(self.source_observation_ids),
            "reversal_condition": self.reversal_condition,
            "shadow_value": self.shadow_value,
            "shadow_observation_ids": list(self.shadow_observation_ids),
            "shadow_refreshes": self.shadow_refreshes,
            "last_supported_refresh": self.last_supported_refresh,
            "lineage": [thaw_json(item) for item in self.lineage],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PreferenceEntry":
        expected = {
            "key",
            "value",
            "status",
            "precedence",
            "source_observation_ids",
            "reversal_condition",
            "shadow_value",
            "shadow_observation_ids",
            "shadow_refreshes",
            "last_supported_refresh",
            "lineage",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PreferenceValidationError("profile entry fields do not match schema")
        if value["status"] not in {"candidate", "active", "contested", "stale"}:
            raise PreferenceValidationError("profile entry status is invalid")
        if value["precedence"] not in {"inferred", "current-explicit"}:
            raise PreferenceValidationError("profile entry precedence is invalid")
        return cls(
            key=_text(value["key"], "key"),
            value=_text(value["value"], "value"),
            status=value["status"],
            precedence=value["precedence"],
            source_observation_ids=tuple(value["source_observation_ids"]),
            reversal_condition=_text(value["reversal_condition"], "reversal_condition"),
            shadow_value=value["shadow_value"],
            shadow_observation_ids=tuple(value["shadow_observation_ids"]),
            shadow_refreshes=int(value["shadow_refreshes"]),
            last_supported_refresh=int(value["last_supported_refresh"]),
            lineage=tuple(thaw_json(item) for item in value["lineage"]),
        )


@dataclass(frozen=True, slots=True)
class UserPreferenceProfile:
    project_id: str
    revision: int
    observation_ids: tuple[str, ...]
    pending_observation_ids: tuple[str, ...]
    entries: tuple[PreferenceEntry, ...]
    last_refresh_turn: int
    next_refresh_turn: int
    previous_revision: int | None
    content_hash: str

    @classmethod
    def create(cls, **values: Any) -> "UserPreferenceProfile":
        values = dict(values)
        supplied_hash = values.pop("content_hash", None)
        values.pop("schema_version", None)
        values.pop("kind", None)
        entries = tuple(
            item if isinstance(item, PreferenceEntry) else PreferenceEntry.from_dict(item) for item in values["entries"]
        )
        normalized = {
            "schema_version": PREFERENCE_SCHEMA_VERSION,
            "kind": USER_PREFERENCE_PROFILE_KIND,
            "project_id": validate_identifier(values["project_id"], "project_id"),
            "revision": int(values["revision"]),
            "observation_ids": list(values["observation_ids"]),
            "pending_observation_ids": list(values["pending_observation_ids"]),
            "entries": [item.to_dict() for item in sorted(entries, key=lambda item: item.key)],
            "last_refresh_turn": int(values["last_refresh_turn"]),
            "next_refresh_turn": int(values["next_refresh_turn"]),
            "previous_revision": values["previous_revision"],
        }
        if normalized["revision"] < 0 or normalized["last_refresh_turn"] < 0 or normalized["next_refresh_turn"] < 5:
            raise PreferenceValidationError("profile revisions and refresh turns are invalid")
        content_hash = _hash(normalized)
        if supplied_hash is not None and supplied_hash != content_hash:
            raise PreferenceValidationError("profile digest mismatch")
        return cls(
            project_id=normalized["project_id"],
            revision=normalized["revision"],
            observation_ids=tuple(normalized["observation_ids"]),
            pending_observation_ids=tuple(normalized["pending_observation_ids"]),
            entries=entries,
            last_refresh_turn=normalized["last_refresh_turn"],
            next_refresh_turn=normalized["next_refresh_turn"],
            previous_revision=normalized["previous_revision"],
            content_hash=content_hash,
        )

    @classmethod
    def empty(
        cls,
        project_id: str,
        *,
        revision: int = 0,
        previous_revision: int | None = None,
        observation_ids: Sequence[str] = (),
    ) -> "UserPreferenceProfile":
        return cls.create(
            project_id=project_id,
            revision=revision,
            observation_ids=observation_ids,
            pending_observation_ids=(),
            entries=(),
            last_refresh_turn=0,
            next_refresh_turn=5,
            previous_revision=previous_revision,
        )

    def entry(self, key: str) -> PreferenceEntry:
        for item in self.entries:
            if item.key == key:
                return item
        raise KeyError(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREFERENCE_SCHEMA_VERSION,
            "kind": USER_PREFERENCE_PROFILE_KIND,
            "project_id": self.project_id,
            "revision": self.revision,
            "observation_ids": list(self.observation_ids),
            "pending_observation_ids": list(self.pending_observation_ids),
            "entries": [item.to_dict() for item in sorted(self.entries, key=lambda item: item.key)],
            "last_refresh_turn": self.last_refresh_turn,
            "next_refresh_turn": self.next_refresh_turn,
            "previous_revision": self.previous_revision,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UserPreferenceProfile":
        expected = {
            "schema_version",
            "kind",
            "project_id",
            "revision",
            "observation_ids",
            "pending_observation_ids",
            "entries",
            "last_refresh_turn",
            "next_refresh_turn",
            "previous_revision",
            "content_hash",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise PreferenceValidationError("profile fields do not match schema")
        if value["schema_version"] != 1 or value["kind"] != USER_PREFERENCE_PROFILE_KIND:
            raise PreferenceValidationError("profile schema identity is invalid")
        return cls.create(**thaw_json(value))


class PreferenceService:
    """Persist and refresh one bounded preference profile per project."""

    def __init__(self, workspace: str | Path, *, stale_after_refreshes: int = 3) -> None:
        if stale_after_refreshes < 1:
            raise ValueError("stale_after_refreshes must be positive")
        self.ledger = RunLedger(workspace)
        self.ledger.initialize()
        self.stale_after_refreshes = stale_after_refreshes

    def inspect(self, project_id: str) -> UserPreferenceProfile:
        payload = self.ledger.load_preference_profile(project_id)
        return UserPreferenceProfile.empty(project_id) if payload is None else UserPreferenceProfile.from_dict(payload)

    def list_observations(self, project_id: str) -> tuple[PreferenceObservation, ...]:
        return tuple(
            PreferenceObservation.from_dict(item) for item in self.ledger.load_preference_observations(project_id)
        )

    def observe(self, observation: PreferenceObservation) -> UserPreferenceProfile:
        if not isinstance(observation, PreferenceObservation):
            raise PreferenceValidationError("observation must be PreferenceObservation")
        current = self.inspect(observation.project_id)
        if observation.observation_id in current.observation_ids:
            existing = next(
                item
                for item in self.list_observations(observation.project_id)
                if item.observation_id == observation.observation_id
            )
            if existing != observation:
                raise PreferenceValidationError("observation id conflict")
            return current
        entries = {item.key: item for item in current.entries}
        pending = list(current.pending_observation_ids)
        if observation.basis == "explicit":
            entries[observation.key] = self._apply_explicit(
                entries.get(observation.key), observation, observation.turn_number // 5
            )
        else:
            pending.append(observation.observation_id)
        next_profile = UserPreferenceProfile.create(
            project_id=current.project_id,
            revision=current.revision + 1,
            observation_ids=(*current.observation_ids, observation.observation_id),
            pending_observation_ids=pending,
            entries=tuple(entries.values()),
            last_refresh_turn=current.last_refresh_turn,
            next_refresh_turn=current.next_refresh_turn,
            previous_revision=current.revision or None,
        )
        observations = (*self.list_observations(observation.project_id), observation)
        while observation.turn_number >= next_profile.next_refresh_turn:
            next_profile = self._refresh(next_profile, observations, boundary=next_profile.next_refresh_turn)
        self.ledger.append_preference_state(observation.to_dict(), next_profile.to_dict())
        return next_profile

    @staticmethod
    def strategy_influences(
        profile: UserPreferenceProfile, *, current_explicit: Mapping[str, str] | None = None
    ) -> tuple[dict[str, Any], ...]:
        """Build content-bound influence lineage with current explicit precedence."""

        explicit = dict(current_explicit or {})
        result: list[dict[str, Any]] = []
        for entry in sorted(profile.entries, key=lambda item: item.key):
            if entry.status == "candidate":
                continue
            selected = explicit.get(entry.key, entry.value)
            result.append(
                {
                    "profile_revision": profile.revision,
                    "observation_id": entry.source_observation_ids[-1],
                    "key": entry.key,
                    "selected_value": selected,
                    "precedence": "current-explicit" if entry.key in explicit else "profile",
                    "reversal_condition": entry.reversal_condition,
                }
            )
        return tuple(result)

    def correct(
        self, *, project_id: str, key: str, value: str, turn_number: int, source_ref: str, reversal_condition: str
    ) -> UserPreferenceProfile:
        current = self.inspect(project_id)
        prior = next((item for item in current.entries if item.key == key), None)
        digest = sha256(canonical_json_bytes([project_id, key, value, turn_number, source_ref])).hexdigest()[:12]
        item = PreferenceObservation.create(
            observation_id=f"correction-{digest}",
            project_id=project_id,
            turn_number=turn_number,
            key=key,
            value=value,
            basis="explicit",
            source_ref=source_ref,
            privacy="project-local",
            reversal_condition=reversal_condition,
            supersedes_observation_id=prior.source_observation_ids[-1] if prior else None,
        )
        return self.observe(item)

    def reset(self, project_id: str) -> UserPreferenceProfile:
        current = self.inspect(project_id)
        reset = UserPreferenceProfile.empty(
            project_id,
            revision=current.revision + 1,
            previous_revision=current.revision or None,
            observation_ids=current.observation_ids,
        )
        self.ledger.append_preference_profile(reset.to_dict())
        return reset

    def delete(self, project_id: str) -> None:
        self.ledger.delete_preference_project(project_id)

    @staticmethod
    def _apply_explicit(
        current: PreferenceEntry | None, observation: PreferenceObservation, refresh_index: int
    ) -> PreferenceEntry:
        lineage = current.lineage if current else ()
        if current:
            lineage = (
                *lineage,
                {
                    "cause": "explicit-supersession",
                    "observation_ids": [observation.observation_id],
                    "before": {"status": current.status, "value": current.value},
                    "after": {"status": "active", "value": observation.value},
                },
            )
        return PreferenceEntry(
            key=observation.key,
            value=observation.value,
            status="active",
            precedence="current-explicit",
            source_observation_ids=(observation.observation_id,),
            reversal_condition=observation.reversal_condition,
            last_supported_refresh=refresh_index,
            lineage=lineage,
        )

    def _refresh(
        self, profile: UserPreferenceProfile, observations: Sequence[PreferenceObservation], *, boundary: int
    ) -> UserPreferenceProfile:
        pending_set = set(profile.pending_observation_ids)
        eligible = [
            item for item in observations if item.observation_id in pending_set and item.turn_number <= boundary
        ]
        remaining = [
            item
            for item in profile.pending_observation_ids
            if item not in {observation.observation_id for observation in eligible}
        ]
        grouped: dict[str, list[PreferenceObservation]] = {}
        for item in eligible:
            grouped.setdefault(item.key, []).append(item)
        entries = {item.key: item for item in profile.entries}
        refresh_index = boundary // 5
        for key, items in grouped.items():
            counts = Counter(item.value for item in items)
            selected = max(
                counts,
                key=lambda value: (counts[value], max(item.turn_number for item in items if item.value == value)),
            )
            selected_items = [item for item in items if item.value == selected]
            entries[key] = self._advance(entries.get(key), selected, selected_items, refresh_index)
        for key, entry in tuple(entries.items()):
            if (
                key not in grouped
                and entry.status in {"active", "contested"}
                and (refresh_index - entry.last_supported_refresh >= self.stale_after_refreshes)
            ):
                entries[key] = replace(
                    entry,
                    status="stale",
                    lineage=(
                        *entry.lineage,
                        {
                            "cause": "aging",
                            "observation_ids": [],
                            "before": {"status": entry.status, "value": entry.value},
                            "after": {"status": "stale", "value": entry.value},
                        },
                    ),
                )
        return UserPreferenceProfile.create(
            project_id=profile.project_id,
            revision=profile.revision,
            observation_ids=profile.observation_ids,
            pending_observation_ids=remaining,
            entries=tuple(entries.values()),
            last_refresh_turn=boundary,
            next_refresh_turn=boundary + 5,
            previous_revision=profile.previous_revision,
        )

    @staticmethod
    def _advance(
        current: PreferenceEntry | None, value: str, observations: Sequence[PreferenceObservation], refresh_index: int
    ) -> PreferenceEntry:
        ids = tuple(item.observation_id for item in observations)
        reversal = observations[-1].reversal_condition
        if current is None:
            return PreferenceEntry(
                key=observations[-1].key,
                value=value,
                status="candidate",
                precedence="inferred",
                source_observation_ids=ids,
                reversal_condition=reversal,
                last_supported_refresh=refresh_index,
            )
        before = {"status": current.status, "value": current.value}
        if value == current.value:
            status = "active" if current.status in {"candidate", "contested", "stale"} else current.status
            result = replace(
                current,
                status=status,
                precedence="inferred",
                source_observation_ids=(*current.source_observation_ids, *ids),
                shadow_value=None,
                shadow_observation_ids=(),
                shadow_refreshes=0,
                last_supported_refresh=refresh_index,
            )
        elif current.status == "contested" and current.shadow_value == value and current.shadow_refreshes >= 1:
            result = replace(
                current,
                value=value,
                status="active",
                precedence="inferred",
                source_observation_ids=(*current.shadow_observation_ids, *ids),
                reversal_condition=reversal,
                shadow_value=None,
                shadow_observation_ids=(),
                shadow_refreshes=0,
                last_supported_refresh=refresh_index,
            )
        else:
            result = replace(
                current,
                status="contested",
                shadow_value=value,
                shadow_observation_ids=ids,
                shadow_refreshes=current.shadow_refreshes + 1,
                last_supported_refresh=refresh_index,
            )
        after = {"status": result.status, "value": result.value}
        return replace(
            result,
            lineage=(
                *result.lineage,
                {
                    "cause": "five-turn-refresh",
                    "observation_ids": list(ids),
                    "before": before,
                    "after": after,
                },
            ),
        )
