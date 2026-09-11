"""Brief refinery: the typed topic/constraint registry (issue #524).

User utterances enter the alignment graph as homogeneous nodes, so gate
semantics cannot differ by type. The user ruling: topics and constraints are
**algorithmically extracted and aggregated** (refined brief processing) —
never user-declared structure; the only user action allowed is confirming a
mirror of their own words.

Engine/model split (deterministic vs generative, per the #501 two-layer
contract — no keyword enums): the engine owns the object schema, equivalence
clustering (through :func:`research_tree.claims.cluster_identity_groups` —
no second clustering implementation), conflict-pair detection, the lifecycle
state machine, persistence, and the signal queries. The model owns
extraction boundaries and the strength/type judgment: it produces candidate
atoms as plain mappings, :meth:`BriefRefinery.extract` validates them
against a strict whitelist schema and applies the conservative defaults. A
wrong initial guess weakens a signal at worst — it can never block.

Conservative defaults: every extracted object starts ``preference`` or
``environment-claim`` — never ``hard-constraint``; a candidate requesting
``hard-constraint`` is downgraded to ``preference``. The upgrade runs only
through :meth:`BriefRefinery.confirm_hard_constraint` with a recorded
confirmation reference.

Lifecycle: ``open → clarified / parked / dropped / merged`` with
``parked → open`` reactivation; terminal states admit nothing, and illegal
transitions are rejected fail-closed naming the rejected transition.

Persistence follows the ``alignment_turn_record`` store pattern:
``brief-registry.json`` under the run's ``alignment/`` directory
(``project_workspace.RUN_DIRECTORIES``), engine-written with a SHA-256
digest over the object state, read fail-closed.

Signal queries feed the adaptive-stance controller: ``vagueness()`` (share
of live objects still open/parked) and ``conflicts()`` (live conflict-pair
count). ``closure_blockers()`` is the additive seam the recursive_search
blocker machinery can consume later — only **confirmed** ``hard-constraint``
violations are named; nothing here wires it into a closure gate.

Stdlib-only per ADR-001. Errors are this module's own.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .claims import cluster_identity_groups

__all__ = [
    "REGISTRY_FILENAME",
    "REGISTRY_SCHEMA_VERSION",
    "LIFECYCLE_TRANSITIONS",
    "BriefRefinery",
    "BriefRefineryStore",
    "RefineryObject",
    "ObjectType",
    "ObjectStatus",
    "RefineryError",
    "ExtractionSchemaError",
    "IllegalLifecycleTransition",
    "ConfirmationRequiredError",
    "RegistryDigestError",
    "registry_digest",
]

REGISTRY_FILENAME = "brief-registry.json"
REGISTRY_SCHEMA_VERSION = 1
REGISTRY_PAYLOAD_KEYS = frozenset({"schema", "objects", "digest"})

# Mirrors alignment_graph.IDENTIFIER_RE / alignment_turn_record.NODE_ID_RE
# so registry object ids can serve as turn-record delta nodes unchanged.
OBJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

ENVELOPE_KEYS = frozenset({"candidates"})
CANDIDATE_KEYS = frozenset({"statement", "topic", "polarity", "requested_type", "anchors", "equivalence_keys"})
REQUIRED_CANDIDATE_KEYS = CANDIDATE_KEYS - {"equivalence_keys"}
REQUESTED_TYPES = frozenset({"preference", "environment-claim", "hard-constraint"})
POLARITIES = frozenset({"positive", "negative"})

OBJECT_KEYS = frozenset(
    {
        "id",
        "statement",
        "topic",
        "polarity",
        "type",
        "status",
        "anchors",
        "equivalence_keys",
        "merged_into",
        "confirmation_ref",
    }
)


class RefineryError(ValueError):
    """A brief-registry value, transition, or file violates the registry schema."""


class ExtractionSchemaError(RefineryError):
    """A model-produced candidate atom (or the extraction envelope) is malformed."""


class IllegalLifecycleTransition(RefineryError):
    """A lifecycle transition is not allowed by the state machine (fail-closed)."""


class ConfirmationRequiredError(RefineryError):
    """A hard-constraint upgrade was attempted without a confirmation reference."""


class RegistryDigestError(RefineryError):
    """The persisted registry file fails its digest verification (fail-closed)."""


class ObjectType(StrEnum):
    PREFERENCE = "preference"
    ENVIRONMENT_CLAIM = "environment-claim"
    HARD_CONSTRAINT = "hard-constraint"


class ObjectStatus(StrEnum):
    OPEN = "open"
    PARKED = "parked"
    CLARIFIED = "clarified"
    DROPPED = "dropped"
    MERGED = "merged"


# Lifecycle state machine: parked may reactivate; terminal states admit nothing.
LIFECYCLE_TRANSITIONS: Mapping[ObjectStatus, frozenset[ObjectStatus]] = {
    ObjectStatus.OPEN: frozenset(
        {ObjectStatus.CLARIFIED, ObjectStatus.PARKED, ObjectStatus.DROPPED, ObjectStatus.MERGED}
    ),
    ObjectStatus.PARKED: frozenset({ObjectStatus.OPEN}),
    ObjectStatus.CLARIFIED: frozenset(),
    ObjectStatus.DROPPED: frozenset(),
    ObjectStatus.MERGED: frozenset(),
}

# Merging an object away requires an open→merged transition, so only open
# objects participate in equivalence clustering; parked/clarified objects are
# settled and dropped/merged objects are history.
_CLUSTERABLE_STATUSES = frozenset({ObjectStatus.OPEN})
_HISTORY_STATUSES = frozenset({ObjectStatus.DROPPED, ObjectStatus.MERGED})


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _text(value: Any, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RefineryError(error)
    return value.strip()


def _string_tuple(value: Any, error: str, *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise RefineryError(error)
    if not allow_empty and not value:
        raise RefineryError(error)
    result = tuple(_text(item, error) for item in value)
    if len(set(result)) != len(result):
        raise RefineryError(f"{error}: duplicates")
    return result


def _merge_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


@dataclass(frozen=True, slots=True)
class RefineryObject:
    """One refined brief atom: an independently negotiable statement with its type."""

    id: str
    statement: str
    topic: str
    polarity: str
    type: ObjectType
    status: ObjectStatus
    anchors: tuple[str, ...]
    equivalence_keys: tuple[str, ...]
    merged_into: str | None = None
    confirmation_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or OBJECT_ID_RE.fullmatch(self.id) is None:
            raise RefineryError(f"brief-registry object id must be an identifier: {self.id!r}")
        object.__setattr__(
            self, "statement", _text(self.statement, "brief-registry statement must be a non-empty string")
        )
        object.__setattr__(self, "topic", _text(self.topic, "brief-registry topic must be a non-empty string"))
        if self.polarity not in POLARITIES:
            raise RefineryError(f"brief-registry polarity must be one of {sorted(POLARITIES)}: {self.polarity!r}")
        if not isinstance(self.type, ObjectType):
            raise RefineryError(f"brief-registry type must be an ObjectType: {self.type!r}")
        if not isinstance(self.status, ObjectStatus):
            raise RefineryError(f"brief-registry status must be an ObjectStatus: {self.status!r}")
        object.__setattr__(
            self,
            "anchors",
            _string_tuple(self.anchors, "brief-registry anchors must be non-empty strings", allow_empty=False),
        )
        object.__setattr__(
            self,
            "equivalence_keys",
            _string_tuple(
                self.equivalence_keys, "brief-registry equivalence_keys must be non-empty strings", allow_empty=True
            ),
        )
        if self.merged_into is not None:
            if not isinstance(self.merged_into, str) or OBJECT_ID_RE.fullmatch(self.merged_into) is None:
                raise RefineryError(f"brief-registry merged_into must be an object id: {self.merged_into!r}")
        if (self.status is ObjectStatus.MERGED) != (self.merged_into is not None):
            raise RefineryError(
                f"brief-registry object {self.id}: merged_into is required exactly when status is merged"
            )
        if (self.type is ObjectType.HARD_CONSTRAINT) != (self.confirmation_ref is not None):
            raise RefineryError(
                f"brief-registry object {self.id}: hard-constraint type requires a confirmation reference "
                "and only hard-constraint objects carry one"
            )
        if self.confirmation_ref is not None:
            object.__setattr__(
                self,
                "confirmation_ref",
                _text(self.confirmation_ref, "brief-registry confirmation_ref must be a non-empty string"),
            )

    @property
    def normalized_topic(self) -> str:
        return _normalize(self.topic)

    @property
    def normalized_statement(self) -> str:
        return _normalize(self.statement)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "topic": self.topic,
            "polarity": self.polarity,
            "type": self.type.value,
            "status": self.status.value,
            "anchors": list(self.anchors),
            "equivalence_keys": list(self.equivalence_keys),
            "merged_into": self.merged_into,
            "confirmation_ref": self.confirmation_ref,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RefineryObject":
        if not isinstance(value, Mapping) or set(value) != OBJECT_KEYS:
            raise RefineryError(f"brief-registry object field mismatch; expected exactly {sorted(OBJECT_KEYS)}")
        try:
            return cls(
                id=value["id"],
                statement=value["statement"],
                topic=value["topic"],
                polarity=value["polarity"],
                type=ObjectType(value["type"]),
                status=ObjectStatus(value["status"]),
                anchors=value["anchors"],
                equivalence_keys=value["equivalence_keys"],
                merged_into=value["merged_into"],
                confirmation_ref=value["confirmation_ref"],
            )
        except ValueError as error:
            raise RefineryError(f"brief-registry object is invalid: {error}") from error


def registry_digest(objects_payload: Sequence[Mapping[str, Any]]) -> str:
    """SHA-256 over the canonical JSON of the registry's object state."""

    canonical = json.dumps(list(objects_payload), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _CandidateAtom:
    """One schema-validated model-produced candidate (pre-registration)."""

    statement: str
    topic: str
    normalized_statement: str
    polarity: str
    object_type: ObjectType
    anchors: tuple[str, ...]
    equivalence_keys: tuple[str, ...]


class BriefRefinery:
    """Engine-side registry of typed topic/constraint objects for one run.

    Extraction consumes model-produced candidate atoms (schema-validated,
    conservative defaults applied, equivalence-merged through the claims
    union-find surface); the lifecycle state machine, the confirmation
    upgrade, the signal queries, and the closure-blocker seam are all pure
    registry operations. Change records accumulate for the turn-record
    delta seam (``alignment_turn_record.registry_delta``).
    """

    def __init__(self, objects: Sequence[RefineryObject] = ()) -> None:
        self._objects: dict[str, RefineryObject] = {}
        self._changes: list[dict[str, str]] = []
        for object_ in objects:
            if not isinstance(object_, RefineryObject):
                raise RefineryError("brief registry objects must be RefineryObject values")
            if object_.id in self._objects:
                raise RefineryError(f"brief registry holds duplicate object ids: {object_.id}")
            self._objects[object_.id] = object_
        for object_ in self._objects.values():
            if object_.merged_into is not None and object_.merged_into not in self._objects:
                raise RefineryError(
                    f"brief registry object {object_.id} merges into unknown object {object_.merged_into}"
                )

    # -- reads ---------------------------------------------------------------

    def objects(self) -> list[RefineryObject]:
        """All registered objects (including merged/dropped history), in insertion order."""

        return list(self._objects.values())

    def object(self, object_id: str) -> RefineryObject:
        if object_id not in self._objects:
            raise RefineryError(f"unknown brief-registry object: {object_id!r}")
        return self._objects[object_id]

    def changes(self) -> tuple[dict[str, str], ...]:
        """Registry change records since construction (the turn-record delta input)."""

        return tuple(dict(change) for change in self._changes)

    def digest(self) -> str:
        return registry_digest([object_.to_dict() for object_ in self._objects.values()])

    def vagueness(self) -> float:
        """Share of live objects (not dropped, not merged) still open or parked."""

        live = self._live_objects()
        if not live:
            return 0.0
        unresolved = sum(1 for object_ in live if object_.status in {ObjectStatus.OPEN, ObjectStatus.PARKED})
        return unresolved / len(live)

    def conflicts(self) -> int:
        """Live conflict pairs: same normalized topic, opposite polarity."""

        polarity_counts: dict[str, dict[str, int]] = {}
        for object_ in self._live_objects():
            counts = polarity_counts.setdefault(object_.normalized_topic, {"positive": 0, "negative": 0})
            counts[object_.polarity] += 1
        return sum(counts["positive"] * counts["negative"] for counts in polarity_counts.values())

    def closure_blockers(self, observations: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], ...]:
        """Name violations of confirmed hard-constraints only (additive seam).

        Each observation is ``{"topic", "polarity", "ref"}``; an observation
        opposes an object when the normalized topics match and the polarity
        differs. Unconfirmed objects never block, so the recursive_search
        blocker machinery can consume this query without re-checking types.
        """

        parsed = self._parse_observations(observations)
        blockers: list[dict[str, str]] = []
        for observation in parsed:
            for object_ in self._objects.values():
                if object_.type is not ObjectType.HARD_CONSTRAINT or object_.status in _HISTORY_STATUSES:
                    continue
                if object_.confirmation_ref is None:  # defense in depth; the type invariant already forbids it
                    continue
                if (
                    object_.normalized_topic == observation["normalized_topic"]
                    and object_.polarity != observation["polarity"]
                ):
                    blockers.append({"object_id": object_.id, "observation_ref": observation["ref"]})
        return tuple(blockers)

    # -- ingestion seam --------------------------------------------------------

    def extract(self, input: Mapping[str, Any]) -> list[RefineryObject]:
        """Validate model-produced candidate atoms and register the refined objects.

        Fail-closed: a malformed batch raises before anything is registered.
        Returns the newly created objects (survivors and born-merged) in
        registration order. Equivalent atoms — same normalized statement or
        a shared equivalence key, clustered through
        :func:`research_tree.claims.cluster_identity_groups` — merge into the
        first-seen member; merged-away objects are born ``merged`` and the
        survivor absorbs their anchors and equivalence keys.
        """

        atoms = self._parse_candidates(input)
        assigned = self._assign_ids(atoms)
        items: list[tuple[str, tuple[str, ...]]] = [
            (
                object_.id,
                (object_.normalized_statement, *object_.equivalence_keys),
            )
            for object_ in self._objects.values()
            if object_.status in _CLUSTERABLE_STATUSES
        ]
        items.extend(
            (object_id, (atom_.normalized_statement, *atom_.equivalence_keys))
            for atom_, object_id in zip(atoms, assigned)
        )
        atom_by_id = dict(zip(assigned, atoms))
        key_owner: dict[str, list[str]] = {}
        for member, keys in items:
            for key in keys:
                key_owner.setdefault(key, []).append(member)

        created: list[RefineryObject] = []
        for survivor, identities in cluster_identity_groups(items):
            member_set = {member for key in identities for member in key_owner[key]}
            ordered_members = [member for member, _keys in items if member in member_set]
            absorbed_anchors: list[str] = []
            absorbed_keys: list[str] = []
            for member in ordered_members:
                if member == survivor:
                    continue
                existing = self._objects.get(member)
                if existing is not None:
                    self._merge_existing(survivor, existing, absorbed_anchors, absorbed_keys)
                    continue
                atom_ = atom_by_id[member]
                _merge_unique(absorbed_anchors, atom_.anchors)
                _merge_unique(absorbed_keys, atom_.equivalence_keys)
                merged = RefineryObject(
                    id=member,
                    statement=atom_.statement,
                    topic=atom_.topic,
                    polarity=atom_.polarity,
                    type=atom_.object_type,
                    status=ObjectStatus.MERGED,
                    anchors=atom_.anchors,
                    equivalence_keys=atom_.equivalence_keys,
                    merged_into=survivor,
                )
                self._objects[member] = merged
                self._changes.append({"action": "registered", "object_id": member})
                created.append(merged)
            survivor_atom = atom_by_id.get(survivor)
            if survivor_atom is not None:
                anchors = list(survivor_atom.anchors)
                keys = list(survivor_atom.equivalence_keys)
                _merge_unique(anchors, absorbed_anchors)
                _merge_unique(keys, absorbed_keys)
                registered = RefineryObject(
                    id=survivor,
                    statement=survivor_atom.statement,
                    topic=survivor_atom.topic,
                    polarity=survivor_atom.polarity,
                    type=survivor_atom.object_type,
                    status=ObjectStatus.OPEN,
                    anchors=tuple(anchors),
                    equivalence_keys=tuple(keys),
                )
                self._objects[survivor] = registered
                self._changes.append({"action": "registered", "object_id": survivor})
                created.append(registered)
            elif absorbed_anchors or absorbed_keys:
                existing = self._objects[survivor]
                anchors = list(existing.anchors)
                keys = list(existing.equivalence_keys)
                _merge_unique(anchors, absorbed_anchors)
                _merge_unique(keys, absorbed_keys)
                self._objects[survivor] = replace(existing, anchors=tuple(anchors), equivalence_keys=tuple(keys))
        return created

    def _merge_existing(
        self,
        survivor: str,
        existing: RefineryObject,
        absorbed_anchors: list[str],
        absorbed_keys: list[str],
    ) -> None:
        """Fold an existing open object into ``survivor`` through the lifecycle."""

        _merge_unique(absorbed_anchors, existing.anchors)
        _merge_unique(absorbed_keys, existing.equivalence_keys)
        self.transition(existing.id, ObjectStatus.MERGED)
        merged = replace(self._objects[existing.id], merged_into=survivor)
        self._objects[existing.id] = merged

    # -- lifecycle -------------------------------------------------------------

    def transition(self, object_id: str, to_status: str | ObjectStatus) -> RefineryObject:
        current = self.object(object_id)
        try:
            target = to_status if isinstance(to_status, ObjectStatus) else ObjectStatus(to_status)
        except ValueError:
            raise RefineryError(f"unknown lifecycle status: {to_status!r}") from None
        allowed = LIFECYCLE_TRANSITIONS[current.status]
        if target not in allowed:
            raise IllegalLifecycleTransition(
                f"illegal lifecycle transition {current.status.value}→{target.value} for object {object_id}; "
                f"allowed from {current.status.value}: {sorted(status.value for status in allowed)}"
            )
        updated = replace(current, status=target)
        self._objects[object_id] = updated
        self._changes.append({"action": "transitioned", "object_id": object_id})
        return updated

    def confirm_hard_constraint(self, object_id: str, confirmation_ref: str | None = None) -> RefineryObject:
        """Upgrade an object to ``hard-constraint`` — the only path that produces one.

        Requires a non-empty confirmation reference (the recorded trace or
        dialogue anchor of the discrimination-class confirmation); refuses
        without one. Re-confirming replaces the reference (latest
        confirmation wins); dropped or merged objects are history and refuse.
        """

        current = self.object(object_id)
        if not isinstance(confirmation_ref, str) or not confirmation_ref.strip():
            raise ConfirmationRequiredError(
                f"confirmation reference required to upgrade object {object_id} to hard-constraint; "
                "the upgrade runs only through a recorded confirmation of the user's own words"
            )
        if current.status in _HISTORY_STATUSES:
            raise RefineryError(
                f"cannot confirm object {object_id} with status {current.status.value}; "
                "dropped and merged objects are history"
            )
        updated = replace(current, type=ObjectType.HARD_CONSTRAINT, confirmation_ref=confirmation_ref.strip())
        self._objects[object_id] = updated
        self._changes.append({"action": "confirmed", "object_id": object_id})
        return updated

    # -- internals ---------------------------------------------------------------

    def _live_objects(self) -> list[RefineryObject]:
        return [object_ for object_ in self._objects.values() if object_.status not in _HISTORY_STATUSES]

    def _parse_candidates(self, input: Mapping[str, Any]) -> list[_CandidateAtom]:
        if not isinstance(input, Mapping) or set(input) != ENVELOPE_KEYS:
            raise ExtractionSchemaError("extraction input must be a mapping with exactly the key 'candidates'")
        candidates = input["candidates"]
        if isinstance(candidates, (str, bytes)) or not isinstance(candidates, list):
            raise ExtractionSchemaError("extraction input candidates must be a list of candidate atoms")
        return [self._parse_candidate(candidate, index) for index, candidate in enumerate(candidates)]

    def _parse_candidate(self, candidate: Any, index: int) -> _CandidateAtom:
        label = f"candidate {index}"
        if not isinstance(candidate, Mapping):
            raise ExtractionSchemaError(f"{label} must be a mapping")
        unknown = set(candidate) - CANDIDATE_KEYS
        missing = REQUIRED_CANDIDATE_KEYS - set(candidate)
        if unknown or missing:
            raise ExtractionSchemaError(
                f"{label} field mismatch; missing: {sorted(missing)}, unknown: {sorted(unknown)}"
            )
        statement = _text(candidate["statement"], f"{label} statement must be a non-empty string")
        topic = _text(candidate["topic"], f"{label} topic must be a non-empty string")
        normalized_statement = _normalize(statement)
        normalized_topic = _normalize(topic)
        if not normalized_statement or not normalized_topic:
            raise ExtractionSchemaError(f"{label} statement and topic must contain alphanumeric content")
        if candidate["polarity"] not in POLARITIES:
            raise ExtractionSchemaError(
                f"{label} polarity must be one of {sorted(POLARITIES)}: {candidate['polarity']!r}"
            )
        if candidate["requested_type"] not in REQUESTED_TYPES:
            raise ExtractionSchemaError(
                f"{label} requested_type must be one of {sorted(REQUESTED_TYPES)}: {candidate['requested_type']!r}"
            )
        anchors = _string_tuple(candidate["anchors"], f"{label} anchors must be non-empty strings", allow_empty=False)
        equivalence_keys = _string_tuple(
            candidate.get("equivalence_keys", []),  # optional key; absence is an empty key set
            f"{label} equivalence_keys must be non-empty strings",
            allow_empty=True,
        )
        # Conservative default: a candidate requesting hard-constraint is downgraded
        # to preference; only the confirmation path produces a hard-constraint.
        object_type = (
            ObjectType.PREFERENCE
            if candidate["requested_type"] == "hard-constraint"
            else ObjectType(candidate["requested_type"])
        )
        return _CandidateAtom(
            statement=statement,
            topic=topic,
            normalized_statement=normalized_statement,
            polarity=candidate["polarity"],
            object_type=object_type,
            anchors=anchors,
            equivalence_keys=equivalence_keys,
        )

    def _parse_observations(self, observations: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], ...]:
        if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
            raise RefineryError("closure blocker observations must be a sequence of mappings")
        parsed: list[dict[str, str]] = []
        for index, observation in enumerate(observations):
            if not isinstance(observation, Mapping) or set(observation) != {"topic", "polarity", "ref"}:
                raise RefineryError(f"observation {index} must contain exactly topic, polarity, and ref")
            topic = _text(observation["topic"], f"observation {index} topic must be a non-empty string")
            if observation["polarity"] not in POLARITIES:
                raise RefineryError(
                    f"observation {index} polarity must be one of {sorted(POLARITIES)}: {observation['polarity']!r}"
                )
            ref = _text(observation["ref"], f"observation {index} ref must be a non-empty string")
            parsed.append({"normalized_topic": _normalize(topic), "polarity": observation["polarity"], "ref": ref})
        return tuple(parsed)

    def _assign_ids(self, atoms: Sequence[_CandidateAtom]) -> list[str]:
        used = set(self._objects)
        assigned: list[str] = []
        for atom_ in atoms:
            base = "ref-" + hashlib.sha256(atom_.normalized_statement.encode("utf-8")).hexdigest()[:12]
            object_id = base
            disambiguator = 0
            while object_id in used:
                disambiguator += 1
                object_id = f"{base}-{disambiguator}"
            used.add(object_id)
            assigned.append(object_id)
        return assigned


class BriefRefineryStore:
    """Engine-written JSON persistence for one run's brief registry (fail-closed).

    Follows the ``alignment_turn_record`` store pattern: the registry lives
    under the run's ``alignment/`` directory, writes are atomic (temporary
    file + ``os.replace``, mode 0600), and loading verifies the SHA-256
    digest over the object state — a missing file is a fresh empty registry,
    a schema or digest mismatch refuses the load.
    """

    def __init__(self, run_root: Path) -> None:
        self.run_root = Path(run_root)
        self.alignment_directory = self.run_root / "alignment"
        self.registry_path = self.alignment_directory / REGISTRY_FILENAME

    def save(self, refinery: BriefRefinery) -> str:
        """Persist the registry and return the recorded digest."""

        if not isinstance(refinery, BriefRefinery):
            raise RefineryError("BriefRefineryStore.save requires a BriefRefinery")
        objects_payload = [object_.to_dict() for object_ in refinery.objects()]
        digest = registry_digest(objects_payload)
        payload = {"schema": REGISTRY_SCHEMA_VERSION, "objects": objects_payload, "digest": digest}
        self.alignment_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_name(f".{self.registry_path.name}.{os.getpid()}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n")
            os.replace(temporary, self.registry_path)
        finally:
            temporary.unlink(missing_ok=True)
        return digest

    def load(self) -> BriefRefinery:
        """Load the registry, verifying the digest; missing file means empty."""

        if not self.registry_path.is_file():
            return BriefRefinery()
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RefineryError(f"brief registry is not valid JSON: {self.registry_path}: {error}") from error
        if not isinstance(payload, Mapping) or set(payload) != REGISTRY_PAYLOAD_KEYS:
            raise RefineryError(
                f"brief registry field mismatch; expected exactly {sorted(REGISTRY_PAYLOAD_KEYS)}: {self.registry_path}"
            )
        if payload["schema"] != REGISTRY_SCHEMA_VERSION:
            raise RefineryError(f"brief registry schema must be {REGISTRY_SCHEMA_VERSION}: {self.registry_path}")
        if not isinstance(payload["objects"], list):
            raise RefineryError(f"brief registry objects must be a list: {self.registry_path}")
        recorded = payload["digest"]
        computed = registry_digest(payload["objects"])
        if recorded != computed:
            raise RegistryDigestError(
                f"brief registry digest mismatch: recorded {recorded!r}, computed {computed!r} "
                f"({self.registry_path} was edited outside the engine)"
            )
        objects: list[RefineryObject] = []
        for index, entry in enumerate(payload["objects"]):
            try:
                objects.append(RefineryObject.from_dict(entry))
            except RefineryError as error:
                raise RefineryError(f"brief registry object {index} is invalid: {error}") from error
        return BriefRefinery(objects)
