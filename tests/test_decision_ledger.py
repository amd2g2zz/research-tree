from __future__ import annotations

from pathlib import Path

import pytest

from canonical_finding_fixture import canonical_context
from research_tree import ArtifactRef
from research_tree.claims import Claim, ClaimGrounding
from research_tree.evidence import EvidenceAnchor, EvidenceArtifact


def api():
    from research_tree import (
        CanonicalDecisionLedgerCompiler,
        CanonicalFindingPackCompiler,
        InvalidDecisionLedgerError,
        InvalidFindingPackError,
        RunLedger,
    )

    return {
        "CanonicalDecisionLedgerCompiler": CanonicalDecisionLedgerCompiler,
        "CanonicalFindingPackCompiler": CanonicalFindingPackCompiler,
        "InvalidDecisionLedgerError": InvalidDecisionLedgerError,
        "InvalidFindingPackError": InvalidFindingPackError,
        "RunLedger": RunLedger,
    }


def repository(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "agent.py").write_text(
        "def run() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'fixture'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    return root


def slot() -> dict[str, object]:
    return {
        "id": "slot-isolation",
        "kind": "architecture",
        "question": "Which isolation boundary should the first agent use?",
        "intent_hypothesis_ids": ["intent-agent"],
        "priority": "P0",
        "impact": "high",
        "uncertainty": "high",
        "irreversibility": "high",
        "constraints": [
            {
                "kind": "input",
                "ref": "input-brief",
                "statement": "The first implementation must remain safe.",
            }
        ],
        "alternatives": ["isolated-worker", "in-process"],
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "greenfield_assumptions": [],
        "depends_on": [],
        "evidence_standard": "repository inspection plus a bounded spike",
        "validation": {"kind": "spike", "oracle": "one fixture crosses the selected boundary"},
        "closure_rule": "select, conditionally select, defer with fallback, or block",
        "status": "open",
        "bounded_research_need": "compare both alternatives against the current boundary",
        "fallback": "retain the current boundary until this decision closes",
    }


def context(tmp_path: Path):
    modules = api()
    store, resolver, round_record, _model, _brief, target, work, _finding, _decision, _evidence, anchor = (
        canonical_context(
            tmp_path,
            include_decision=False,
        )
    )
    modules["resolver"] = resolver
    modules["anchor"] = anchor
    return modules, store, round_record, target, work


def finding_payload(option: str, effect: str, claim: str) -> dict[str, object]:
    return {
        "observations": [
            {
                "claim": claim,
                "anchor": {"kind": "repository", "ref": "src/agent.py:run"},
                "applicability": "the supplied Python repository",
                "confidence": "medium",
                "limitation": "This does not measure production throughput.",
            }
        ],
        "option_effects": [{"option": option, "effect": effect}],
        "implementation_implications": ["The run boundary needs an explicit adapter."],
        "remaining_uncertainties": ["Measure startup overhead with a spike."],
    }


def compile_finding(modules, store, round_record, work, finding_id: str, **payload):
    claim = Claim(
        claim_id=f"claim-{finding_id}",
        subject="source",
        predicate="supports",
        value="the isolated worker boundary",
        polarity="positive",
        scope="fixture boundary",
        version="fixture-v1",
        time_range="fixture-time",
    )
    observations = []
    for value in payload["observations"]:
        observation = dict(value)
        observation["claim_id"] = claim.claim_id
        observation["anchor"] = modules["anchor"].to_dict()
        observations.append(observation)
    independent_ref = ArtifactRef(round_record.id, "strict-source-independent", 1)
    independent = EvidenceArtifact.from_revision(independent_ref, store.get_artifact(independent_ref))
    independent_anchor = EvidenceAnchor(
        artifact_ref=independent_ref,
        artifact_digest=independent.content_digest,
        artifact_revision=1,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="fixture-reader-v1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
    effects = []
    for value in payload["option_effects"]:
        effect = dict(value)
        effect["claim_ids"] = [claim.claim_id]
        effects.append(effect)
    return modules["CanonicalFindingPackCompiler"](store, modules["resolver"]).compile(
        round_id=round_record.id,
        finding_id=finding_id,
        work_item=work,
        observations=observations,
        expected_revision=store.get_revision(round_record.id),
        option_effects=effects,
        implementation_implications=payload["implementation_implications"],
        remaining_uncertainties=payload["remaining_uncertainties"],
        claims=[claim],
        claim_groundings=[
            ClaimGrounding(f"grounding-{finding_id}", claim.claim_id, modules["anchor"].to_dict()),
            ClaimGrounding(f"grounding-{finding_id}-independent", claim.claim_id, independent_anchor.to_dict()),
        ],
    )


def converge(modules, store, round_record, **kwargs):
    return modules["CanonicalDecisionLedgerCompiler"](store, modules["resolver"]).converge(
        round_id=round_record.id,
        expected_revision=store.get_revision(round_record.id),
        **kwargs,
    )


def decision_kwargs(target, findings) -> dict[str, object]:
    return {
        "blueprint_target": target,
        "decision_slot_id": "slot-isolation",
        "finding_packs": findings,
        "status": "conditional",
        "selected_option": "isolated-worker",
        "alternatives": [
            {
                "option": "in-process",
                "disposition": "deferred",
                "reason": "Conflicting evidence leaves startup cost unmeasured.",
            }
        ],
        "anchors": [{"kind": "finding", "ref": finding.id} for finding in findings],
        "design_consequence": "Add a worker adapter at src/agent.py:run.",
        "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
        "validation": {"kind": "spike", "oracle": "one fixture completes through the worker adapter"},
        "change_tasks": [
            {
                "id": "change-worker-adapter",
                "description": "Introduce the selected isolation adapter.",
                "acceptance_oracle": "The fixture crosses the adapter with no direct binary execution.",
                "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}],
            }
        ],
        "assumptions": ["The local worker boundary is sufficient for the first demo."],
        "fallback": "Keep the in-process boundary behind a feature flag.",
        "reversal_condition": "A spike shows worker startup overhead breaks the first workflow.",
        "revision_reason": "Initial convergence from bounded isolation research.",
    }


def test_atomic_finding_pack_preserves_exact_work_lineage_and_rejects_bare_source_list(
    tmp_path: Path,
) -> None:
    modules, store, round_record, _target, work = context(tmp_path)
    finding = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-support",
        **finding_payload("isolated-worker", "supports", "The run boundary can be adapted to a worker."),
    )

    assert finding.kind == "finding-pack"
    assert finding.payload["work_item_id"] == work.id
    assert finding.parent_refs[0].revision == work.revision
    invalid = finding_payload("isolated-worker", "supports", "A source URL alone is not evidence.")
    invalid["observations"] = []
    with pytest.raises(modules["InvalidFindingPackError"]):
        compile_finding(modules, store, round_record, work, "finding-bare-source", **invalid)


def test_conflicting_findings_remain_inspectable_under_conditional_decision(tmp_path: Path) -> None:
    modules, store, round_record, target, work = context(tmp_path)
    support = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-support",
        **finding_payload("isolated-worker", "supports", "The worker boundary isolates execution."),
    )
    contradiction = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-contradiction",
        **finding_payload("isolated-worker", "contradicts", "Startup cost may exceed the first-demo budget."),
    )
    decision = converge(
        modules,
        store,
        round_record,
        decision_id="decision-isolation",
        **decision_kwargs(target, [support, contradiction]),
    )

    assert decision.kind == "decision-ledger-entry"
    assert decision.payload["status"] == "conditional"
    assert [anchor["ref"] for anchor in decision.payload["anchors"] if anchor["kind"] == "finding"] == [
        support.id,
        contradiction.id,
    ]
    assert {reference.artifact_id for reference in decision.parent_refs} >= {
        target.id,
        support.id,
        contradiction.id,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("alternatives", []),
        ("anchors", []),
        ("change_tasks", []),
        ("fallback", ""),
        ("reversal_condition", ""),
    ],
)
def test_p0_decision_requires_traceable_alternatives_and_reversal(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    modules, store, round_record, target, work = context(tmp_path)
    finding = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-support",
        **finding_payload("isolated-worker", "supports", "The worker boundary isolates execution."),
    )
    invalid = decision_kwargs(target, [finding])
    invalid[field] = value

    with pytest.raises(modules["InvalidDecisionLedgerError"]):
        converge(
            modules,
            store,
            round_record,
            decision_id="decision-isolation",
            **invalid,
        )

    assert [
        artifact for artifact in store.load_run(round_record.id).artifacts if artifact.kind == "decision-ledger-entry"
    ] == []


def test_blocked_p0_can_record_fallback_without_finding_packs(tmp_path: Path) -> None:
    modules, _store, round_record, target, _work = context(tmp_path)
    blocked = decision_kwargs(target, [])
    blocked.update(
        {
            "status": "blocked",
            "selected_option": None,
            "alternatives": [
                {
                    "option": "isolated-worker",
                    "disposition": "deferred",
                    "reason": "The required experiment environment is unavailable.",
                }
            ],
            "anchors": [],
            "change_tasks": [],
            "revision_reason": "Record the blocked path with a usable fallback.",
        }
    )

    decision = converge(
        modules,
        _store,
        round_record,
        decision_id="decision-isolation",
        **blocked,
    )
    assert decision.payload["status"] == "blocked"
    assert decision.payload["fallback"]


def test_p0_selected_option_requires_a_finding_effect_for_that_option(tmp_path: Path) -> None:
    modules, store, round_record, target, work = context(tmp_path)
    unrelated = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-in-process",
        **finding_payload("in-process", "supports", "Only the in-process option has evidence."),
    )

    with pytest.raises(modules["InvalidDecisionLedgerError"]):
        converge(
            modules,
            store,
            round_record,
            decision_id="decision-isolation",
            **decision_kwargs(target, [unrelated]),
        )


def test_reversed_decision_appends_revision_without_mutating_prior_conclusion(tmp_path: Path) -> None:
    modules, store, round_record, target, work = context(tmp_path)
    first_finding = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-first",
        **finding_payload("isolated-worker", "supports", "The worker boundary isolates execution."),
    )
    first = converge(
        modules,
        store,
        round_record,
        decision_id="decision-isolation",
        **decision_kwargs(target, [first_finding]),
    )
    reversal_finding = compile_finding(
        modules,
        store,
        round_record,
        work,
        "finding-reversal",
        **finding_payload("in-process", "supports", "The local in-process boundary meets the measured budget."),
    )
    revised = decision_kwargs(target, [first_finding, reversal_finding])
    revised.update(
        {
            "status": "selected",
            "selected_option": "in-process",
            "alternatives": [
                {
                    "option": "isolated-worker",
                    "disposition": "rejected",
                    "reason": "The new spike exceeded the first-demo startup budget.",
                }
            ],
            "revision_reason": "New spike evidence reverses the conditional choice.",
        }
    )
    second = converge(
        modules,
        store,
        round_record,
        decision_id="decision-isolation",
        **revised,
    )

    artifacts = modules["RunLedger"](tmp_path / "ledger").load_run(round_record.id).artifacts
    stored_first = next(
        artifact for artifact in artifacts if artifact.id == first.id and artifact.revision == first.revision
    )
    assert [first.revision, second.revision] == [1, 2]
    assert second.parent_refs[0].revision == first.revision
    assert stored_first.payload["selected_option"] == "isolated-worker"
