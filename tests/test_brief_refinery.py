"""Brief refinery: the typed topic/constraint registry (issue #524).

The issue's scenarios, named after them: extraction of a multi-statement
brief yields atomic, clustered, typed objects with conservative defaults
(every object starts preference/environment-claim — never hard-constraint);
lifecycle illegal transitions are rejected fail-closed naming the
transition; the confirmation upgrade requires a confirmation reference;
equivalence merge reuses the claims.py union-find surface; conflict pairs
are detected deterministically; vagueness/conflict queries return
registry-derived numbers; persistence round-trips with a digest and fails
closed on tampering; only confirmed hard-constraint violations become
closure blockers; and registry changes convert into a turn-record delta
payload. The model side is a test double: candidate atoms arrive as plain
mappings, the engine only validates schema (no keyword enums, per the #501
two-layer contract).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research_tree.alignment_turn_record import (
    AlignmentTurnRecordStore,
    TurnRecordError,
    registry_delta,
)
from research_tree.brief_refinery import (
    BriefRefinery,
    BriefRefineryStore,
    ConfirmationRequiredError,
    ExtractionSchemaError,
    IllegalLifecycleTransition,
    RefineryError,
    RegistryDigestError,
)
from research_tree.claims import cluster_identity_groups
from research_tree.turn_contract import RESPONSE_CLASS_GENERATION

RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")


def atom(
    statement: str,
    *,
    topic: str = "offline-support",
    polarity: str = "positive",
    requested_type: str = "preference",
    anchors: tuple[str, ...] = ("turn-1",),
    equivalence_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """A model-produced candidate atom (the test double's extraction output)."""

    return {
        "statement": statement,
        "topic": topic,
        "polarity": polarity,
        "requested_type": requested_type,
        "anchors": list(anchors),
        "equivalence_keys": list(equivalence_keys),
    }


def run_root(tmp_path: Path) -> Path:
    root = tmp_path.joinpath(*RUN_ROOT_PARTS)
    root.mkdir(parents=True, exist_ok=True)
    return root


def by_statement(objects: list[Any]) -> dict[str, Any]:
    return {object.statement: object for object in objects}


def test_extraction_yields_atomic_clustered_typed_objects_with_conservative_defaults() -> None:
    refinery = BriefRefinery()
    objects = refinery.extract(
        {
            "candidates": [
                atom(
                    "must run without any network connection",
                    requested_type="hard-constraint",
                    anchors=("turn-1",),
                ),
                atom(
                    "prefer a lightweight install",
                    topic="install-weight",
                    equivalence_keys=("install-weight",),
                    anchors=("turn-1",),
                ),
                atom(
                    "I heard the exporter fails on large files",
                    topic="exporter",
                    polarity="negative",
                    requested_type="environment-claim",
                    anchors=("turn-1",),
                ),
                atom(
                    "a lightweight install is preferred",
                    topic="install-weight",
                    equivalence_keys=("install-weight",),
                    anchors=("turn-2",),
                ),
            ]
        }
    )
    assert len(objects) == 4
    assert len({object.id for object in objects}) == 4
    # Conservative defaults: a candidate requesting hard-constraint is downgraded,
    # and no extraction path ever registers a hard-constraint object.
    assert all(object.type in {"preference", "environment-claim"} for object in objects)
    assert by_statement(objects)["must run without any network connection"].type == "preference"
    assert by_statement(objects)["I heard the exporter fails on large files"].type == "environment-claim"
    # Equivalent candidates merge into one live object; the merged-away object
    # records merged_into and the survivor absorbs its anchors.
    survivor = by_statement(objects)["prefer a lightweight install"]
    merged_away = by_statement(objects)["a lightweight install is preferred"]
    assert survivor.status == "open"
    assert merged_away.status == "merged"
    assert merged_away.merged_into == survivor.id
    assert survivor.anchors == ("turn-1", "turn-2")
    assert refinery.object(survivor.id) == survivor


def test_malformed_candidate_rejected_fail_closed() -> None:
    assert issubclass(ExtractionSchemaError, RefineryError)
    assert issubclass(RegistryDigestError, RefineryError)
    refinery = BriefRefinery()
    with pytest.raises(ExtractionSchemaError, match="candidate 1"):
        refinery.extract({"candidates": [atom("runs offline"), {"statement": "no topic"}]})
    with pytest.raises(ExtractionSchemaError, match="requested_type"):
        refinery.extract({"candidates": [atom("runs offline", requested_type="must-have")]})
    with pytest.raises(ExtractionSchemaError, match="candidate"):
        refinery.extract({"candidates": [atom("runs offline")], "extra": 1})
    # Fail-closed: nothing from the rejected batch is registered.
    assert refinery.objects() == []
    # The optional equivalence_keys key may be omitted entirely.
    (registered,) = refinery.extract(
        {
            "candidates": [
                {
                    "statement": "runs offline",
                    "topic": "offline",
                    "polarity": "positive",
                    "requested_type": "preference",
                    "anchors": ["turn-1"],
                }
            ]
        }
    )
    assert registered.type == "preference" and registered.equivalence_keys == ()


def test_lifecycle_illegal_transitions_rejected_fail_closed() -> None:
    refinery = BriefRefinery()
    (first,) = refinery.extract({"candidates": [atom("runs offline")]})
    (second,) = refinery.extract({"candidates": [atom("installs quickly", topic="install")]})
    refinery.transition(first.id, "clarified")
    # open→open is illegal and names the rejected transition; state unchanged.
    with pytest.raises(IllegalLifecycleTransition, match=r"open→open"):
        refinery.transition(second.id, "open")
    assert refinery.object(second.id).status == "open"
    # Terminal states admit nothing.
    with pytest.raises(IllegalLifecycleTransition, match=r"clarified→parked"):
        refinery.transition(first.id, "parked")
    assert refinery.object(first.id).status == "clarified"
    # parked reactivates to open.
    refinery.transition(second.id, "parked")
    refinery.transition(second.id, "open")
    assert refinery.object(second.id).status == "open"
    # dropped is terminal.
    refinery.transition(second.id, "dropped")
    with pytest.raises(IllegalLifecycleTransition, match=r"dropped→open"):
        refinery.transition(second.id, "open")
    assert refinery.object(second.id).status == "dropped"


def test_confirmation_upgrade_requires_confirmation_ref() -> None:
    refinery = BriefRefinery()
    (extracted,) = refinery.extract(
        {"candidates": [atom("must run without any network connection", requested_type="hard-constraint")]}
    )
    assert extracted.type == "preference"
    for bad_ref in (None, "", "   "):
        with pytest.raises(ConfirmationRequiredError, match="confirmation"):
            refinery.confirm_hard_constraint(extracted.id, bad_ref)  # type: ignore[arg-type]
        assert refinery.object(extracted.id).type == "preference"
    refinery.confirm_hard_constraint(extracted.id, "turn-3:option-set-a")
    confirmed = refinery.object(extracted.id)
    assert confirmed.type == "hard-constraint"
    assert confirmed.confirmation_ref == "turn-3:option-set-a"


def test_equivalence_merge_via_claims_clustering() -> None:
    # The shared union-find surface: items sharing any identity key join one
    # component; the first-seen member names it.
    assert cluster_identity_groups([("a", ("k1",)), ("b", ("k2",)), ("c", ("k1", "k2"))]) == (
        ("a", frozenset({"k1", "k2"})),
    )
    refinery = BriefRefinery()
    (existing,) = refinery.extract(
        {
            "candidates": [
                atom("export large repositories in one pass", topic="export", equivalence_keys=("export-bulk",))
            ]
        }
    )
    (paraphrase,) = refinery.extract(
        {
            "candidates": [
                atom(
                    "bulk export for large repositories",
                    topic="export",
                    equivalence_keys=("export-bulk",),
                    anchors=("turn-2",),
                )
            ]
        }
    )
    (duplicate,) = refinery.extract({"candidates": [atom("export large repositories in one pass", topic="export")]})
    assert paraphrase.status == "merged"
    assert paraphrase.merged_into == existing.id
    assert duplicate.status == "merged"
    assert duplicate.merged_into == existing.id
    survivor = refinery.object(existing.id)
    assert survivor.anchors == ("turn-1", "turn-2")
    assert [object.id for object in refinery.objects() if object.merged_into is None] == [existing.id]


def test_conflict_pair_detection_deterministic() -> None:
    refinery = BriefRefinery()
    (positive,) = refinery.extract({"candidates": [atom("runs offline")]})
    (negative,) = refinery.extract(
        {"candidates": [atom("cannot run offline", topic="Offline  Support", polarity="negative")]}
    )
    # Same normalized topic (case/spacing folded), opposite polarity: one pair.
    assert refinery.conflicts() == 1
    (second_positive,) = refinery.extract({"candidates": [atom("works without a network", anchors=("turn-2",))]})
    assert refinery.conflicts() == 2
    # Dropped objects leave the conflict count: dropping one positive leaves
    # the other opposing pair, dropping the negative ends the conflict.
    refinery.transition(positive.id, "dropped")
    assert refinery.conflicts() == 1
    refinery.transition(negative.id, "dropped")
    assert refinery.conflicts() == 0
    assert {positive.id, negative.id, second_positive.id}  # ids stable for audit


def test_vagueness_and_conflict_queries_reflect_registry_state() -> None:
    refinery = BriefRefinery()
    assert refinery.vagueness() == 0.0
    objects = refinery.extract(
        {
            "candidates": [
                atom("runs offline"),
                atom("installs quickly", topic="install"),
                atom("exports pdf", topic="export"),
                atom("imports csv", topic="import"),
            ]
        }
    )
    assert refinery.vagueness() == 1.0
    refinery.transition(objects[0].id, "clarified")
    assert refinery.vagueness() == 0.75
    refinery.transition(objects[1].id, "parked")
    assert refinery.vagueness() == 0.75
    refinery.transition(objects[2].id, "dropped")
    # Dropped objects leave the denominator; the parked object stays vague.
    assert refinery.vagueness() == pytest.approx(2 / 3)


def test_persistence_round_trip_with_digest(tmp_path: Path) -> None:
    store = BriefRefineryStore(run_root(tmp_path))
    refinery = BriefRefinery()
    objects = refinery.extract(
        {
            "candidates": [
                atom("must run without any network connection", requested_type="hard-constraint"),
                atom("prefer a lightweight install", topic="install-weight"),
            ]
        }
    )
    refinery.confirm_hard_constraint(objects[0].id, "turn-3:option-set-a")
    digest = store.save(refinery)
    assert digest == refinery.digest()
    loaded = store.load()
    assert loaded.objects() == refinery.objects()
    assert loaded.digest() == digest
    # Tampered registry fails closed naming the digest mismatch.
    payload = json.loads(store.registry_path.read_text(encoding="utf-8"))
    payload["objects"][0]["statement"] = "edited outside the engine"
    store.registry_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RegistryDigestError, match="digest"):
        store.load()
    # A missing registry file loads as a fresh empty registry.
    assert BriefRefineryStore(run_root(tmp_path) / "other-run").load().objects() == []


def test_only_confirmed_hard_constraint_violations_block_closure() -> None:
    refinery = BriefRefinery()
    (constraint,) = refinery.extract(
        {"candidates": [atom("must run without any network connection", requested_type="hard-constraint")]}
    )
    observation = {"topic": "offline support", "polarity": "negative", "ref": "obs-1"}
    # Unconfirmed objects never block — not even one that requested hard-constraint.
    assert refinery.closure_blockers([observation]) == ()
    refinery.confirm_hard_constraint(constraint.id, "turn-3:option-set-a")
    assert refinery.closure_blockers([observation]) == ({"object_id": constraint.id, "observation_ref": "obs-1"},)
    # Same polarity and unrelated topics do not oppose.
    assert refinery.closure_blockers([{**observation, "polarity": "positive"}]) == ()
    assert refinery.closure_blockers([{**observation, "topic": "install", "ref": "obs-2"}]) == ()


def test_registry_changes_become_turn_record_delta(tmp_path: Path) -> None:
    refinery = BriefRefinery()
    objects = refinery.extract(
        {
            "candidates": [
                atom("must run without any network connection", requested_type="hard-constraint"),
                atom("prefer a lightweight install", topic="install-weight"),
            ]
        }
    )
    refinery.confirm_hard_constraint(objects[0].id, "turn-3:option-set-a")
    refinery.transition(objects[1].id, "parked")
    changes = refinery.changes()
    assert changes
    payload = registry_delta(changes)
    assert set(payload) == {"summary", "nodes"}
    assert "registered" in payload["summary"] and "confirmed" in payload["summary"]
    assert payload["nodes"] == [object.id for object in objects]
    store = AlignmentTurnRecordStore(run_root(tmp_path))
    record = store.append(
        turn_index=1,
        mirror="the brief names an offline requirement and an install preference",
        gap="whether the offline requirement is hard",
        delta_summary=payload["summary"],
        delta_nodes=payload["nodes"],
        user_move=RESPONSE_CLASS_GENERATION,
    )
    assert record.delta == {"summary": payload["summary"], "nodes": payload["nodes"]}
    with pytest.raises(TurnRecordError, match="empty"):
        registry_delta([])
    # Registry object ids must satisfy the turn-record node identifier rules.
    with pytest.raises(TurnRecordError, match="node id"):
        registry_delta([{"action": "registered", "object_id": "not a node id!"}])
