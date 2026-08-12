from copy import deepcopy

import pytest

from research_tree import AcceptanceError, validate_semantic_deliveries


def _manifest():
    claim = {
        "claim_id": "claim-fact-1", "class": "fact", "text": "The repository exposes src/agent.py:run",
        "surfaces": ["technical", "human"], "selectors": ["technical.findings[0]", "human.evidence[0]"],
        "decision_refs": [], "finding_refs": ["finding-1@1"], "evidence_refs": ["source:src/agent.py:run"],
        "oracle_refs": [], "boundary_ref": None, "next_validation": None,
    }
    recommendation = {
        "claim_id": "claim-recommendation-1", "class": "recommendation", "text": "Use an isolated worker boundary",
        "surfaces": ["technical", "human"], "selectors": ["technical.decisions[0]", "human.direction[0]"],
        "decision_refs": ["decision-1@1"], "finding_refs": ["finding-1@1"], "evidence_refs": ["source:src/agent.py:run"],
        "oracle_refs": ["oracle:worker-fixture"], "boundary_ref": "src/agent.py:run", "next_validation": "Run the isolated-worker fixture.",
    }
    return {
        "technical_revision": "technical-1", "human_revision": "human-1", "source_ledger_digest": "1" * 64,
        "compiler_version": "delivery-compiler-v1", "template_version": "alpha2-v1", "encoding": "UTF-8",
        "output_paths": {"technical": {"locator": "artifact://run-a/technical/1", "sha256": "2" * 64}, "human": {"locator": "artifact://run-a/human/1", "sha256": "3" * 64}},
        "generated_at": "2026-08-06T00:00:00+00:00", "claim_index": [claim, recommendation],
        "depth_assessments": [{"dimension": dimension, "status": "pass", "evidence_refs": ["claim-fact-1"], "diagnostic": "Boundary is explicit", "follow_up": None} for dimension in (
            "problem_fidelity", "evidence_quality", "counterevidence", "alternatives_tradeoffs", "implementation_boundary",
            "risks_failure_modes", "validation_path", "uncertainties", "operational_meaning")],
    }


def _technical():
    return {"kind": "technical-research-package", "manifest": _manifest(), "document": {
        "round_and_scope": {"working_interpretation": "Build a safe autonomous agent."},
        "blueprint_closure": [{"decision_slot_id": "slot-1", "priority": "P0", "status": "selected"}],
        "research_findings": [{"finding_id": "finding-1", "revision": 1, "observations": [{"claim": "The repository exposes src/agent.py:run", "anchor": {"kind": "source", "ref": "src/agent.py:run"}}]}],
        "decision_records": [{"decision_id": "decision-1", "revision": 1, "status": "selected", "selected_option": "Use an isolated worker boundary.", "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}], "validation": {"kind": "test", "oracle": "worker-fixture"}}],
        "implementation_plan": [{"description": "Introduce the worker adapter.", "repository_touchpoints": [{"path": "src/agent.py", "symbol": "run"}], "validation": {"kind": "test", "oracle": "worker-fixture"}}],
        "risks_and_validation": [{"statement": "Process startup may exceed the latency budget.", "validation": "Measure the worker fixture."}],
        "traceability": {"working_brief": {"artifact_id": "brief-1"}},
    }}


def _human():
    return {"kind": "human-research-report", "manifest": _manifest(), "document": {
        "what_was_understood": {"working_interpretation": "Build a safe autonomous agent that can be implemented next."},
        "evidence_and_reasoning": [{"claim": "The repository exposes src/agent.py:run", "evidence_refs": ["source:src/agent.py:run"], "reasoning": "This is the narrowest existing execution boundary.", "limitation": "Startup cost is not measured yet."}],
        "recommended_direction": {"selected_directions": [{"decision_slot_id": "slot-1", "selected_option": "Use an isolated worker boundary."}]},
        "alternatives_and_tradeoffs": [{"selected": "isolated worker", "alternative": "in process", "tradeoff": "Isolation improves containment but adds startup latency."}],
        "expected_capability": {"statement": "A fixture can execute through the isolated boundary.", "evidence_refs": ["claim-recommendation-1"]},
        "applicability": {"applies_to": ["src/agent.py:run"], "does_not_claim": ["Production latency is already acceptable."]},
        "implementation_meaning": {"first_slice": "Introduce the worker adapter.", "touchpoints": ["src/agent.py:run"], "validation": "Run worker-fixture.", "blockers": ["Latency is unmeasured."]},
        "risks_and_uncertainty": [{"statement": "Process startup may exceed the latency budget.", "response": "Measure before rollout."}],
    }}


def test_semantic_delivery_requires_one_professional_pair():
    result = validate_semantic_deliveries(_technical(), _human())
    assert result["status"] == "semantically_ready" and result["claim_count"] == 2
    assert all(item["status"] == "pass" for item in result["depth_assessments"])


def test_semantic_delivery_rejects_legacy_kind_and_manifest_drift():
    with pytest.raises(AcceptanceError, match="legacy"):
        validate_semantic_deliveries(_technical(), _human() | {"kind": "human-brief"})
    human = _human(); human["manifest"] = deepcopy(human["manifest"]); human["manifest"]["human_revision"] = "human-2"
    with pytest.raises(AcceptanceError, match="manifest"):
        validate_semantic_deliveries(_technical(), human)


def test_semantic_delivery_rejects_orphan_claim_and_missing_boundary():
    technical = _technical(); technical["document"]["research_findings"][0]["observations"].append({"claim": "An unindexed consequential fact.", "anchor": {"kind": "source", "ref": "README.md"}})
    with pytest.raises(AcceptanceError, match="orphan_claim"):
        validate_semantic_deliveries(technical, _human())
    technical = _technical(); technical["document"]["implementation_plan"][0]["repository_touchpoints"] = []
    with pytest.raises(AcceptanceError, match="implementation_boundary"):
        validate_semantic_deliveries(technical, _human())


def test_semantic_delivery_rejects_unresolved_p0_and_shallow_human_reasoning():
    technical = _technical(); technical["document"]["blueprint_closure"][0]["status"] = "conditional"
    with pytest.raises(AcceptanceError, match="unresolved_p0"):
        validate_semantic_deliveries(technical, _human())
    human = _human(); human["document"]["evidence_and_reasoning"] = []
    with pytest.raises(AcceptanceError, match="shallow_human_reasoning"):
        validate_semantic_deliveries(_technical(), human)
