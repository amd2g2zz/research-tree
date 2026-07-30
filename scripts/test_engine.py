"""Tests for the intent-constrained recursive research DAG."""

from __future__ import annotations

import io
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402


FRAME = {
    "focus": "company history", "information_gap": "initial facts are unknown",
    "discriminator": "primary company material", "expected_update": "establish timeline",
    "evidence_requirement": "one dated primary source", "priority": 0.8,
    "temporal_scope": {"start": "2023-01-01", "end": "2026-01-01", "field": "published_at"},
}


class EngineTests(unittest.TestCase):
    QUALITY_COMPONENTS = (
        "authority", "directness", "traceability", "temporal_fit",
        "capture_completeness", "independence",
    )
    CONFIDENCE_COMPONENTS = (
        "source_quality", "corroboration", "independence",
        "temporal_coherence", "scope_match",
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-engine-v2-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()
        (self.tmp / "research_drift" / "pages").mkdir(parents=True)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cmd(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(engine.main(list(argv)), 0)
        return json.loads(out.getvalue())

    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded test request requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded test fixture to create its explicit research frames.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def init_state(self, clauses=None):
        result = self.cmd("init", "--intent", "Investigate DeepMind", "--reference-time", "2026-07-29T00:00:00+00:00",
                          "--clauses", json.dumps(clauses or []))
        self.cmd("analyze-intent", "--contract", json.dumps(self.ready_intent_contract()))
        return result

    @classmethod
    def source_assessment(cls, local_path: str, content_sha256: str, *, primary: bool = True,
                          relation: str = "representative", quality: float = 0.8) -> dict:
        return {
            "local_path": local_path,
            "content_sha256": content_sha256,
            "relation": relation,
            "primary": primary,
            "quality_components": {key: quality for key in cls.QUALITY_COMPONENTS},
            "assessment_confidence": 0.9,
            "rationale": "The saved page is a complete, directly relevant source for this bounded topic.",
        }

    @classmethod
    def topic_cluster(cls, topic_key: str, sources: list[dict], representatives: list[str] | None = None) -> dict:
        return {
            "topic_key": topic_key,
            "topic": f"Topic {topic_key}",
            "context_signature": "bounded test source context",
            "dedup_rationale": "Sources are grouped by their substantive claim and context, not their URLs.",
            "sources": sources,
            "representative_local_paths": representatives or [sources[0]["local_path"]],
            "confidence_components": {key: 0.8 for key in cls.CONFIDENCE_COMPONENTS},
            "confidence_rationale": "The bounded topic has directly captured support with explicit provenance.",
            "unresolved": [],
        }

    def aggregate_saved_sources(self, frame_id: str, clusters: list[dict] | None = None,
                                 *, source_manifest_sha256: str | None = None) -> dict:
        state = engine.ResearchState.load()
        frame = state.data["frames"][frame_id]
        manifest_path = self.tmp / frame["collection"]["source_manifest_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if clusters is None:
            clusters = [self.topic_cluster(
                f"saved-source-{index}",
                [self.source_assessment(record["evidence"]["local_path"], record["content_sha256"])],
            ) for index, record in enumerate(manifest["records"]) if record.get("status") == "captured"]
        return self.cmd(
            "aggregate-sources", "--frame", frame_id, "--clusters", json.dumps(clusters),
            "--source-manifest-sha256", source_manifest_sha256 or frame["collection"]["source_manifest_sha256"],
        )

    def begin_saved_source_review(self, frame_id: str, proposals: list[dict] | None = None,
                                  *, aggregate: bool = True) -> None:
        """Create saved collection artifacts and, by default, complete aggregation."""

        state = engine.ResearchState.load()
        if state.data["frames"][frame_id]["state"] == "acquiring":
            discovery = self.tmp / "research_drift" / "discovery" / f"{frame_id}.json"
            manifest = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
            discovery.parent.mkdir(parents=True, exist_ok=True)
            manifest.parent.mkdir(parents=True, exist_ok=True)
            discovery.write_text("{}", encoding="utf-8")
            records = []
            for proposal in proposals or []:
                path = proposal.get("local_path") if isinstance(proposal, dict) else None
                page = self.tmp / path if isinstance(path, str) else None
                if page is None or not page.is_file():
                    continue
                records.append({"status": "captured", "evidence": dict(proposal),
                                "content_sha256": hashlib.sha256(page.read_bytes()).hexdigest()})
            summary = {"candidate_count": len(records), "capture_limit": max(1, len(records)),
                       "captured_count": len(records), "failed_count": 0, "deferred_count": 0}
            manifest.write_text(json.dumps({"schema": 1, "frame_id": frame_id, "request_sha256": "a" * 64,
                                            "records": records, "summary": summary}), encoding="utf-8")
            state.collection_ready(frame_id, {
                "discovery_path": str(discovery.relative_to(self.tmp)).replace("\\", "/"),
                "source_manifest_path": str(manifest.relative_to(self.tmp)).replace("\\", "/"),
                "request_sha256": "a" * 64,
                "summary": summary,
                "review_roles": ["source_triager", "source_adversary"],
            })
            state.save()
        if aggregate and engine.ResearchState.load().data["frames"][frame_id]["state"] == "aggregating":
            self.aggregate_saved_sources(frame_id)

    def submit_review_evidence(self, frame_id: str, proposals: list[dict]) -> dict:
        self.begin_saved_source_review(frame_id, proposals)
        result = self.cmd("evidence", "--frame", frame_id, "--evidence", json.dumps(proposals),
                          "--reviewer-role", "source_triager")
        self.cmd("evidence", "--frame", frame_id, "--evidence", "[]",
                 "--reviewer-role", "source_adversary")
        return result

    def expanded_frame_with_two_gaps(self):
        """Create an expanded root frame with two still-deferred alternatives."""
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "frontier-source.md"
        page.write_text("source", encoding="utf-8")
        evidence_id = self.submit_review_evidence(frame_id, [{
            "local_path": "research_drift/pages/frontier-source.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        extracted = self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
            "proposal_ref": "root-observation", "claim": "one supported observation", "context_signature": "source scope", "evidence_time": "2024-01-01",
            "confidence": 0.5, "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}]), "--gaps", json.dumps([
            {"description": "first discriminating question", "discriminator": "primary source", "expected_update": "resolve first", "evidence_requirement": "official source", "expected_information_gain": 0.8, "trigger_cognition_refs": ["root-observation"]},
            {"description": "second discriminating question", "discriminator": "independent source", "expected_update": "resolve second", "evidence_requirement": "official source", "expected_information_gain": 0.7, "trigger_cognition_refs": ["root-observation"]},
        ]))
        self.assertEqual(extracted["cognition_refs"], {"root-observation": extracted["cognition_ids"][0]})
        gap_ids = extracted["gap_ids"]
        return frame_id, gap_ids

    def decision_intent_contract(self) -> dict:
        contract = self.ready_intent_contract()
        contract["decision_questions"] = [{
            "id": "adoption", "question": "Should the user approve the proposed change now?",
            "why_it_matters": "It determines whether the team commits implementation effort.",
            "impact": "high", "deliverable_ids": ["test-fixture"],
        }]
        return contract

    def decision_ready_frame(self) -> tuple[str, str]:
        self.cmd("init", "--intent", "Evaluate a proposed change", "--reference-time", "2026-07-29T00:00:00+00:00")
        self.cmd("analyze-intent", "--contract", json.dumps(self.decision_intent_contract()))
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "bounded evidence"}]))
        page = self.tmp / "research_drift" / "pages" / "decision-source.md"
        page.write_text("A directly relevant saved source.", encoding="utf-8")
        evidence_id = self.submit_review_evidence(frame_id, [{
            "local_path": "research_drift/pages/decision-source.md", "published_at": "2024-01-01",
        }])["evidence_ids"][0]
        return frame_id, evidence_id

    def test_decision_contract_requires_source_coverage_and_synthesis_before_freeze(self):
        frame_id, evidence_id = self.decision_ready_frame()
        cognition = [{
            "claim": "The saved source supports a bounded preflight only.",
            "context_signature": "direct source scope", "evidence_time": "2024-01-01",
            "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
        }]
        with self.assertRaisesRegex(ValueError, "requires source coverage"):
            self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps(cognition), "--gaps", "[]")
        extracted = self.cmd(
            "extract", "--frame", frame_id, "--cognitions", json.dumps(cognition), "--gaps", "[]",
            "--coverage", json.dumps([{
                "evidence_id": evidence_id, "disposition": "cited",
                "rationale": "It directly supports the bounded conclusion.",
            }]),
        )
        self.cmd("finish", "--frame", frame_id, "--state", "resolved", "--summary", "bounded result", "--confidence", "0.7")
        self.assertEqual(self.cmd("next")["action"], "synthesize_decision")
        with self.assertRaisesRegex(ValueError, "decision synthesis audit"):
            self.cmd("freeze", "--snapshot", "decision-missing")
        synthesis = {
            "overall_status": "conditional", "recommendation": "preflight_only",
            "summary": "Run a preflight, not an adoption decision.",
            "question_assessments": [{
                "decision_question_id": "adoption", "status": "conditional",
                "conclusion": "The evidence supports only a bounded preflight.",
                "supporting_cognition_ids": extracted["cognition_ids"], "refuting_cognition_ids": [],
                "gap_ids": [], "user_questions": [],
                "conditions_to_change": ["Compare the proposed change against the actual baseline."],
                "action": "Run the bounded preflight before any adoption decision.",
            }],
            "parameter_provenance": [],
        }
        result = self.cmd("synthesize-decision", "--synthesis", json.dumps(synthesis))
        self.assertEqual(result["recommendation"], "preflight_only")
        self.assertEqual(self.cmd("next")["action"], "freeze_ready")
        self.assertEqual(self.cmd("freeze", "--snapshot", "decision-ready")["snapshot_id"], "decision-ready")

    def test_decision_contract_rejects_uncovered_followup_and_premature_approval(self):
        frame_id, evidence_id = self.decision_ready_frame()
        cognition = [{
            "proposal_ref": "source-finding", "claim": "The source leaves a critical feasibility gap.",
            "context_signature": "direct source scope", "evidence_time": "2024-01-01",
            "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
        }]
        with self.assertRaisesRegex(ValueError, "must reference a gap"):
            self.cmd(
                "extract", "--frame", frame_id, "--cognitions", json.dumps(cognition), "--gaps", "[]",
                "--coverage", json.dumps([{
                    "evidence_id": evidence_id, "disposition": "needs_followup",
                    "rationale": "A feasibility discriminator is still missing.",
                }]),
            )
        extracted = self.cmd(
            "extract", "--frame", frame_id, "--cognitions", json.dumps(cognition),
            "--gaps", json.dumps([{
                "proposal_ref": "feasibility-gap", "description": "Verify feasibility against the actual baseline.",
                "discriminator": "measured baseline comparison", "expected_update": "changes adoption readiness",
                "evidence_requirement": "saved measured result", "trigger_cognition_refs": ["source-finding"],
            }]),
            "--coverage", json.dumps([{
                "evidence_id": evidence_id, "disposition": "needs_followup",
                "rationale": "A feasibility discriminator is still missing.", "gap_refs": ["feasibility-gap"],
            }]),
        )
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_calls_per_frame"] = 0
        state.save()
        self.cmd("finish", "--frame", frame_id, "--state", "insufficient_evidence", "--summary", "gap retained", "--confidence", "0.2")
        bad = {
            "overall_status": "need_user_input", "recommendation": "approve", "summary": "approve anyway",
            "question_assessments": [{
                "decision_question_id": "adoption", "status": "need_user_input", "conclusion": "Need the baseline.",
                "supporting_cognition_ids": [], "refuting_cognition_ids": [], "gap_ids": extracted["gap_ids"],
                "user_questions": ["Which baseline is authoritative?"], "conditions_to_change": [],
                "action": "Ask for the baseline.",
            }], "parameter_provenance": [],
        }
        with self.assertRaisesRegex(ValueError, "cannot approve"):
            self.cmd("synthesize-decision", "--synthesis", json.dumps(bad))

    def test_ambiguous_hard_clause_blocks_the_next_action(self):
        self.init_state([{"id": "time", "raw": "recent", "status": "ambiguous"}])
        self.cmd("bootstrap", "--frames", json.dumps([FRAME]))
        action = self.cmd("next")
        self.assertEqual(action["action"], "clarify")
        self.cmd("clarify", "--clause", "time", "--status", "enforced", "--interpretation", "past three years")
        self.assertEqual(self.cmd("next")["action"], "formulate")

    def test_ambiguous_clause_does_not_block_an_unaffected_frame(self):
        self.init_state([{"id": "a-only", "raw": "needs user material", "status": "ambiguous"}])
        blocked = dict(FRAME, focus="requires user material", intent_clause_ids=["a-only"])
        runnable = dict(FRAME, focus="independent public history", information_gap="public timeline", intent_clause_ids=[])
        frame_ids = self.cmd("bootstrap", "--frames", json.dumps([blocked, runnable]))["frame_ids"]
        action = self.cmd("next")
        self.assertEqual(action["action"], "formulate")
        self.assertEqual(action["frame"]["id"], frame_ids[1])

    def test_evidence_cognition_gap_and_child_frame_are_versioned(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind history", "constraints": ["c1"]}]))
        page = self.tmp / "research_drift" / "pages" / "deepmind.md"
        page.write_text("DeepMind announced a model in 2024.", encoding="utf-8")
        evidence = self.submit_review_evidence(frame_id, [{
            "url": "https://example.test/deepmind", "title": "DeepMind", "local_path": "research_drift/pages/deepmind.md", "published_at": "2024-05-01"}])
        evidence_id = evidence["evidence_ids"][0]
        extracted = self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
            "proposal_ref": "announcement", "claim": "A model was announced in 2024", "confidence": 0.8,
            "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
            "context_signature": "DeepMind announcement date", "evidence_time": "2024-05-01"}]),
            "--gaps", json.dumps([{
            "description": "Which model was announced?", "discriminator": "official model page",
            "expected_update": "name the model", "evidence_requirement": "one official source",
            "trigger_cognition_refs": ["announcement"]}]))
        self.assertEqual(extracted["cognition_refs"], {"announcement": extracted["cognition_ids"][0]})
        gap_id = extracted["gap_ids"][0]
        child = self.cmd("expand", "--gap", gap_id, "--frame", json.dumps({
            "focus": "identify the announced model", "priority": 0.9}))
        self.assertTrue(child["created"])
        data = engine.ResearchState.load().data
        self.assertEqual(data["gaps"][gap_id]["status"], "expanded")
        self.assertTrue(any(edge["kind"] == "expands_to" for edge in data["derivation_edges"]))

    def test_time_audit_and_freeze_require_terminal_frames(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "dated.md"; page.write_text("dated evidence", encoding="utf-8")
        self.submit_review_evidence(frame_id, [{"local_path": "research_drift/pages/dated.md", "published_at": "2024-01-01"}])
        evidence_id = engine.ResearchState.load().data["frames"][frame_id]["evidence_ids"][0]
        self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
            "claim": "The evidence is dated in 2024", "context_signature": "publication date",
            "evidence_time": "2024-01-01", "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}]), "--gaps", "[]")
        self.assertTrue(self.cmd("time-audit")["ok"])
        self.cmd("finish", "--frame", frame_id, "--state", "resolved", "--summary", "bounded", "--confidence", "0.8")
        frozen = self.cmd("freeze", "--snapshot", "unit")
        self.assertEqual(frozen["snapshot_id"], "unit")

    def test_time_audit_rejects_out_of_range_evidence(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "old.md"; page.write_text("old evidence", encoding="utf-8")
        evidence_id = self.submit_review_evidence(frame_id, [{
            "local_path": "research_drift/pages/old.md", "published_at": "2022-12-31"}])["evidence_ids"][0]
        self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
            "claim": "An old source supports the claim", "context_signature": "dated source",
            "evidence_time": "2022-12-31", "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
        }]), "--gaps", "[]")
        audit = self.cmd("time-audit")
        self.assertFalse(audit["ok"])
        self.assertEqual(audit["issues"][0]["issue"], "published_at outside temporal scope")

    def test_publication_time_enrichment_requires_saved_page_witness(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "dated-in-body.md"
        page.write_text("Submitted on 18 Feb 2024 by the official record.", encoding="utf-8")
        evidence_id = self.submit_review_evidence(frame_id, [{
            "local_path": "research_drift/pages/dated-in-body.md",
        }])["evidence_ids"][0]
        self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
            "claim": "The saved record is dated in the allowed window.", "context_signature": "publication date",
            "evidence_time": "2024-02-18", "source_spans": [{"evidence_id": evidence_id, "locator": "Submitted on 18 Feb 2024"}],
        }]), "--gaps", "[]")
        self.assertFalse(self.cmd("time-audit")["ok"])
        with self.assertRaisesRegex(ValueError, "locator is not present"):
            self.cmd("enrich-evidence-publication-time", "--evidence", evidence_id,
                     "--published-at", "2024-02-18", "--locator", "not in the saved page",
                     "--rationale", "The page carries the primary submission date.")
        result = self.cmd("enrich-evidence-publication-time", "--evidence", evidence_id,
                          "--published-at", "2024-02-18", "--locator", "Submitted on 18 Feb 2024",
                          "--rationale", "The primary record's saved text carries the submission date.")
        self.assertEqual(result["published_at"], "2024-02-18")
        self.assertTrue(self.cmd("time-audit")["ok"])
        state = engine.ResearchState.load().data
        self.assertEqual(state["evidence"][evidence_id]["publication_time_enrichment"]["locator"], "Submitted on 18 Feb 2024")

    def test_frame_identity_includes_gap_and_discriminator(self):
        self.init_state()
        other = dict(FRAME, information_gap="founder identity is unknown")
        frame_ids = self.cmd("bootstrap", "--frames", json.dumps([FRAME, other]))["frame_ids"]
        self.assertEqual(len(set(frame_ids)), 2)

    def test_frame_rejects_an_invalid_temporal_scope_before_search(self):
        self.init_state()
        invalid = dict(FRAME, temporal_scope={"field": "published_at", "start": "2026-02-01", "end": "2026-01-01"})
        with self.assertRaisesRegex(ValueError, "temporal_scope start is after end"):
            self.cmd("bootstrap", "--frames", json.dumps([invalid]))

    def test_evidence_path_must_stay_in_saved_page_store(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        outside = self.tmp / "outside.md"; outside.write_text("not an accepted page", encoding="utf-8")
        self.begin_saved_source_review(frame_id)
        with self.assertRaisesRegex(ValueError, "inside research_drift/pages"):
            self.cmd("evidence", "--frame", frame_id, "--evidence", json.dumps([{
                "local_path": "outside.md", "published_at": "2024-01-01"}]),
                "--reviewer-role", "source_triager")

    def test_aggregation_rejects_a_mismatched_source_manifest_hash(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "hash-bound.md"
        page.write_text("hash-bound saved source", encoding="utf-8")
        self.begin_saved_source_review(frame_id, [{"local_path": "research_drift/pages/hash-bound.md"}], aggregate=False)
        with self.assertRaisesRegex(ValueError, "bind the current source manifest sha256"):
            self.aggregate_saved_sources(frame_id, source_manifest_sha256="b" * 64)
        self.assertEqual(engine.ResearchState.load().data["frames"][frame_id]["state"], "aggregating")

    def test_aggregation_allows_a_non_primary_source_association(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        first_path = "research_drift/pages/cross-topic-first.md"
        second_path = "research_drift/pages/cross-topic-second.md"
        (self.tmp / first_path).write_text("First source supports two related topics.", encoding="utf-8")
        (self.tmp / second_path).write_text("Second source supports the second topic.", encoding="utf-8")
        self.begin_saved_source_review(frame_id, [{"local_path": first_path}, {"local_path": second_path}], aggregate=False)
        state = engine.ResearchState.load()
        manifest = json.loads((self.tmp / state.data["frames"][frame_id]["collection"]["source_manifest_path"]).read_text(encoding="utf-8"))
        hashes = {record["evidence"]["local_path"]: record["content_sha256"] for record in manifest["records"]}
        clusters = [
            self.topic_cluster("primary-topic", [self.source_assessment(first_path, hashes[first_path])]),
            self.topic_cluster(
                "secondary-topic",
                [
                    self.source_assessment(second_path, hashes[second_path]),
                    self.source_assessment(first_path, hashes[first_path], primary=False, relation="corroborating"),
                ],
                [second_path],
            ),
        ]
        result = self.aggregate_saved_sources(frame_id, clusters)
        self.assertEqual(result["state"], "reviewing")
        saved_clusters = result["aggregation"]["clusters"]
        first_assessments = [
            source for cluster in saved_clusters for source in cluster["sources"] if source["local_path"] == first_path
        ]
        self.assertEqual(len(first_assessments), 2)
        self.assertEqual(sum(source["primary"] for source in first_assessments), 1)

    def test_duplicate_saved_evidence_is_reused_across_worker_submissions(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "deduplicated.md"
        page.write_text("one complete source", encoding="utf-8")
        proposal = [{"local_path": "research_drift/pages/deduplicated.md", "published_at": "2024-01-01"}]
        self.begin_saved_source_review(frame_id, proposal)
        first = self.cmd("evidence", "--frame", frame_id, "--evidence", json.dumps(proposal),
                         "--reviewer-role", "source_triager")
        second = self.cmd("evidence", "--frame", frame_id, "--evidence", json.dumps(proposal),
                          "--reviewer-role", "source_adversary")
        self.assertEqual(first["evidence_ids"], second["evidence_ids"])
        state = engine.ResearchState.load().data
        self.assertEqual(len(state["evidence"]), 1)
        self.assertEqual(state["frames"][frame_id]["evidence_ids"], first["evidence_ids"])

    def test_descendant_reuses_content_as_a_new_evidence_version_to_keep_dag_acyclic(self):
        self.init_state()
        parent_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", parent_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "shared.md"
        page.write_text("shared complete source", encoding="utf-8")
        parent_evidence = self.submit_review_evidence(parent_id, [{
            "local_path": "research_drift/pages/shared.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        extracted = self.cmd("extract", "--frame", parent_id, "--cognitions", json.dumps([{
            "claim": "parent observation", "context_signature": "shared source", "evidence_time": "2024-01-01",
            "source_spans": [{"evidence_id": parent_evidence, "locator": "p:1"}],
        }]), "--gaps", "[]")
        state = engine.ResearchState.load()
        state.data["frames"][parent_id]["state"] = "extracting"
        state.save()
        gap_id = self.cmd("extract", "--frame", parent_id, "--cognitions", "[]", "--gaps", json.dumps([{
            "description": "child needs the same source in a narrower context", "discriminator": "source context",
            "expected_update": "compare context", "evidence_requirement": "saved source",
            "trigger_cognition_ids": extracted["cognition_ids"],
        }]))["gap_ids"][0]
        child_id = self.cmd("descend", "--frame", parent_id, "--gap", gap_id, "--child", json.dumps({
            "focus": "child context", "priority": 0.8}), "--rationale", "context needs an explicit child call")["frame_id"]
        self.assertEqual(engine.ResearchState.load().data["frames"][child_id]["temporal_scope"], FRAME["temporal_scope"])
        self.cmd("formulate", "--frame", child_id, "--plan", json.dumps([{"query": "DeepMind context"}]))
        child_evidence = self.submit_review_evidence(child_id, [{
            "local_path": "research_drift/pages/shared.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        self.assertNotEqual(parent_evidence, child_evidence)
        self.assertEqual(len(engine.ResearchState.load().data["evidence"]), 2)

    def test_explicit_contradiction_reopens_a_terminal_frame_frontier(self):
        self.init_state()
        parent_id, other_id = self.cmd("bootstrap", "--frames", json.dumps([
            FRAME,
            {**FRAME, "focus": "counter-evidence", "information_gap": "which result disagrees"},
        ]))["frame_ids"]
        self.cmd("formulate", "--frame", parent_id, "--plan", json.dumps([{"query": "primary claim"}]))
        parent_page = self.tmp / "research_drift" / "pages" / "parent.md"
        parent_page.write_text("parent source", encoding="utf-8")
        parent_evidence = self.submit_review_evidence(parent_id, [{
            "local_path": "research_drift/pages/parent.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        first = self.cmd("extract", "--frame", parent_id, "--cognitions", json.dumps([{
            "claim": "the original result holds", "claim_key": "scaling-result", "polarity": "supports",
            "context_signature": "same metric and model family", "evidence_time": "2024-01-01",
            "source_spans": [{"evidence_id": parent_evidence, "locator": "p:1"}],
        }]), "--gaps", "[]")
        state = engine.ResearchState.load()
        state.data["frames"][parent_id]["state"] = "extracting"
        state.save()
        gap = self.cmd("extract", "--frame", parent_id, "--cognitions", "[]", "--gaps", json.dumps([{
            "description": "test the original result under an independent source", "discriminator": "independent source",
            "expected_update": "change confidence", "evidence_requirement": "saved source",
            "trigger_cognition_ids": first["cognition_ids"],
        }]))["gap_ids"][0]
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_calls_per_frame"] = 0
        state.save()
        self.cmd("finish", "--frame", parent_id, "--state", "resolved", "--summary", "initial result", "--confidence", "0.8")
        self.cmd("formulate", "--frame", other_id, "--plan", json.dumps([{"query": "counter claim"}]))
        other_page = self.tmp / "research_drift" / "pages" / "other.md"
        other_page.write_text("counter source", encoding="utf-8")
        other_evidence = self.submit_review_evidence(other_id, [{
            "local_path": "research_drift/pages/other.md", "published_at": "2025-01-01"}])["evidence_ids"][0]
        result = self.cmd("extract", "--frame", other_id, "--cognitions", json.dumps([{
            "claim": "the original result does not hold under the same context", "claim_key": "scaling-result",
            "polarity": "refutes", "context_signature": "same metric and model family", "evidence_time": "2025-01-01",
            "contradicts_cognition_ids": first["cognition_ids"],
            "source_spans": [{"evidence_id": other_evidence, "locator": "p:1"}],
        }]), "--gaps", "[]")
        self.assertEqual(result["relations"][0]["kind"], "contradicts")
        parent = engine.ResearchState.load().data["frames"][parent_id]
        self.assertEqual(parent["state"], "expanded")
        self.assertEqual(engine.ResearchState.load().data["frontier"][gap]["reactivation_count"], 1)

    def test_resolved_frame_requires_cited_cognition(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        state = engine.ResearchState.load()
        state.data["frames"][frame_id]["state"] = "expanded"
        state.save()
        with self.assertRaisesRegex(ValueError, "requires at least one cited cognition"):
            self.cmd("finish", "--frame", frame_id, "--state", "resolved", "--summary", "unsupported")

    def test_cognition_requires_context_and_evidence_time(self):
        self.init_state()
        frame_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", frame_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "source.md"; page.write_text("source", encoding="utf-8")
        evidence_id = self.submit_review_evidence(frame_id, [{
            "local_path": "research_drift/pages/source.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        with self.assertRaisesRegex(ValueError, "context_signature"):
            self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
                "claim": "claim", "evidence_time": "2024-01-01",
                "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}]), "--gaps", "[]")
        with self.assertRaisesRegex(ValueError, "evidence_time"):
            self.cmd("extract", "--frame", frame_id, "--cognitions", json.dumps([{
                "claim": "claim", "context_signature": "scope",
                "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}]), "--gaps", "[]")

    def test_snapshot_name_must_not_escape_snapshot_store(self):
        self.init_state()
        with self.assertRaisesRegex(ValueError, "snapshot id"):
            self.cmd("freeze", "--snapshot", "../outside")

    def test_recursive_descent_returns_to_parent_without_exhausting_frontier(self):
        self.init_state()
        parent_id = self.cmd("bootstrap", "--frames", json.dumps([FRAME]))["frame_ids"][0]
        self.cmd("formulate", "--frame", parent_id, "--plan", json.dumps([{"query": "DeepMind"}]))
        page = self.tmp / "research_drift" / "pages" / "source.md"
        page.write_text("source", encoding="utf-8")
        evidence_id = self.submit_review_evidence(parent_id, [{
            "local_path": "research_drift/pages/source.md", "published_at": "2024-01-01"}])["evidence_ids"][0]
        extracted = self.cmd("extract", "--frame", parent_id, "--cognitions", json.dumps([{
            "claim": "one supported observation", "context_signature": "source scope", "evidence_time": "2024-01-01",
            "confidence": 0.4, "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}]}]), "--gaps", "[]")
        state = engine.ResearchState.load()
        state.data["frames"][parent_id]["state"] = "extracting"
        state.save()
        extracted = self.cmd("extract", "--frame", parent_id, "--cognitions", "[]",
            "--gaps", json.dumps([
                {"description": "first discriminating question", "discriminator": "primary source", "expected_update": "resolve first", "evidence_requirement": "official source", "expected_information_gain": 0.9, "trigger_cognition_ids": extracted["cognition_ids"]},
                {"description": "deferred alternative", "discriminator": "independent source", "expected_update": "resolve later", "evidence_requirement": "official source", "expected_information_gain": 0.2, "trigger_cognition_ids": extracted["cognition_ids"]},
            ]))
        selected_gap, deferred_gap = extracted["gap_ids"]
        child = self.cmd("descend", "--frame", parent_id, "--gap", selected_gap, "--child", json.dumps({
            "focus": "first child", "priority": 0.8}), "--rationale", "highest expected information gain")
        child_id = child["frame_id"]
        self.assertEqual(engine.ResearchState.load().data["frames"][parent_id]["state"], "waiting_child")
        state = engine.ResearchState.load()
        state.data["frames"][child_id]["state"] = "expanded"
        state.save()
        self.cmd("finish", "--frame", child_id, "--state", "insufficient_evidence", "--summary", "bounded", "--confidence", "0.2")
        self.cmd("return-child", "--frame", parent_id, "--child", child_id, "--rationale", "child did not resolve the parent")
        parent = engine.ResearchState.load().data["frames"][parent_id]
        self.assertEqual(parent["state"], "expanded")
        self.assertEqual(engine.ResearchState.load().data["gaps"][deferred_gap]["status"], "open")
        deferred_frontier = engine.ResearchState.load().data["frontier"][deferred_gap]
        self.assertEqual(deferred_frontier["reactivation_count"], 1)
        self.assertIn("selected child returned low confidence", deferred_frontier["reactivation_reasons"])
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_calls_per_frame"] = 1
        state.save()
        self.cmd("finish", "--frame", parent_id, "--state", "resolved", "--summary", "parent contract met", "--confidence", "0.7")

    def test_clear_frontier_prevents_terminal_return_until_recursive_budget_is_exhausted(self):
        parent_id, _ = self.expanded_frame_with_two_gaps()
        state = engine.ResearchState.load()
        state.data["descent_policy"]["score_margin"] = 0.0
        state.save()
        with self.assertRaisesRegex(ValueError, "clear frontier descent remains"):
            self.cmd("finish", "--frame", parent_id, "--state", "resolved", "--summary", "premature", "--confidence", "0.8")
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_calls_per_frame"] = 0
        state.save()
        self.cmd("finish", "--frame", parent_id, "--state", "resolved", "--summary", "bounded by recursive budget", "--confidence", "0.8")

    def test_score_margin_requests_review_and_allows_explicit_override(self):
        parent_id, gap_ids = self.expanded_frame_with_two_gaps()
        state = engine.ResearchState.load()
        # Deliberately make the deterministic ranking non-decisive.
        state.data["descent_policy"]["score_margin"] = 10.0
        state.save()
        action = self.cmd("next")
        self.assertEqual(action["action"], "choose_descent")
        self.assertEqual(action["decision"]["recommendation"], "review")
        self.assertEqual(action["decision"]["reason_code"], "ambiguous_frontier_scores")
        result = self.cmd("descend", "--frame", parent_id, "--gap", gap_ids[1], "--child", json.dumps({
            "focus": "second child", "priority": 0.8}), "--rationale",
            "the independent discriminator is more likely to expose a contradiction")
        self.assertTrue(result["selection_overrode_recommendation"])
        events = engine.ResearchState.load().data["events"]
        self.assertTrue(any(item["action"] == "frontier_recommendation_overridden" for item in events))
        self.assertEqual(engine.ResearchState.load().data["gaps"][gap_ids[0]]["status"], "open")

    def test_depth_budget_returns_without_pruning_the_deferred_frontier(self):
        parent_id, gap_ids = self.expanded_frame_with_two_gaps()
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_depth"] = 0
        state.save()
        action = self.cmd("next")
        self.assertEqual(action["action"], "return")
        self.assertEqual(action["decision"]["reason_code"], "max_depth_reached")
        with self.assertRaisesRegex(ValueError, "recursive descent blocked"):
            self.cmd("descend", "--frame", parent_id, "--gap", gap_ids[0], "--child", json.dumps({
                "focus": "blocked child", "priority": 0.8}), "--rationale", "try deeper research")
        data = engine.ResearchState.load().data
        self.assertEqual(data["gaps"][gap_ids[0]]["status"], "open")
        self.assertEqual(data["frontier"][gap_ids[0]]["status"], "deferred")

    def test_global_frame_budget_blocks_new_children_but_preserves_candidates(self):
        parent_id, gap_ids = self.expanded_frame_with_two_gaps()
        state = engine.ResearchState.load()
        state.data["descent_policy"]["max_frames"] = 1
        state.save()
        action = self.cmd("next")
        self.assertEqual(action["action"], "return")
        self.assertEqual(action["decision"]["reason_code"], "global_frame_budget_reached")
        self.assertTrue(action["decision"]["allow_existing_merge"])
        with self.assertRaisesRegex(ValueError, "global frame budget exhausted"):
            self.cmd("descend", "--frame", parent_id, "--gap", gap_ids[0], "--child", json.dumps({
                "focus": "new child", "priority": 0.8}), "--rationale", "try a unique child")
        data = engine.ResearchState.load().data
        self.assertEqual(data["gaps"][gap_ids[0]]["status"], "open")
        self.assertEqual(data["frontier"][gap_ids[0]]["status"], "deferred")

    def test_json_argument_file_is_confined_to_the_workspace(self):
        clauses = self.tmp / "clauses.json"
        clauses.write_text('[{"id": "time", "raw": "recent"}]', encoding="utf-8")
        self.cmd("init", "--intent", "Investigate DeepMind", "--clauses", "@clauses.json")
        self.assertEqual(engine.ResearchState.load().active_clauses()[0]["id"], "time")
        with self.assertRaisesRegex(ValueError, "inside the research workspace"):
            engine._read_json("@../outside.json", list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
