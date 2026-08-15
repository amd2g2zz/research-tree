from __future__ import annotations

import pytest

from canonical_finding_fixture import RUN_ID, canonical_context


def test_canonical_blueprint_target_compiler_is_public() -> None:
    from research_tree import CanonicalBlueprintTargetCompiler

    assert CanonicalBlueprintTargetCompiler.__name__ == "CanonicalBlueprintTargetCompiler"


def test_canonical_blueprint_target_requires_current_ledger_revision(tmp_path) -> None:
    from research_tree import CanonicalBlueprintTargetCompiler, LedgerConflictError

    ledger, _resolver, _record, _model, brief, target, *_rest = canonical_context(tmp_path)
    compiler = CanonicalBlueprintTargetCompiler(ledger)
    expected_revision = ledger.get_revision(RUN_ID)
    change = {
        "kind": "initial",
        "reason": "Create an independently addressed canonical target.",
        "from_slot_ids": [],
        "to_slot_ids": ["slot-isolation"],
    }

    written = compiler.compile(
        round_id=RUN_ID,
        target_id="blueprint-target-next",
        working_brief=brief,
        slots=target.payload["slots"],
        change=change,
        expected_revision=expected_revision,
    )

    assert written.parent_refs[-2:] == (
        type(written.parent_refs[0])(RUN_ID, brief.id, brief.revision),
        type(written.parent_refs[0])(RUN_ID, "intent-model", 1),
    )
    with pytest.raises(LedgerConflictError):
        compiler.compile(
            round_id=RUN_ID,
            target_id="blueprint-target-stale",
            working_brief=brief,
            slots=target.payload["slots"],
            change=change,
            expected_revision=expected_revision,
        )
