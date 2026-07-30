"""Tests for the service boundary and LangGraph execution adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from langgraph_runner import build_research_graph, invoke_research_graph, research_graph_config
from research_orchestrator import ResearchOrchestrator
from research_service import ResearchService


FRAME = {
    "focus": "runtime capabilities",
    "information_gap": "which primitives are available",
    "discriminator": "official documentation",
    "expected_update": "define a boundary",
    "evidence_requirement": "official source",
}


class WorkflowTests(unittest.TestCase):
    QUALITY_COMPONENTS = (
        "authority", "directness", "traceability", "temporal_fit",
        "capture_completeness", "independence",
    )
    CONFIDENCE_COMPONENTS = (
        "source_quality", "corroboration", "independence",
        "temporal_coherence", "scope_match",
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-workflow-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()
        self.service = ResearchService()
        self.service.initialize("Investigate an agent", [], "2026-07-29T00:00:00+00:00")
        self.service.analyze_intent(self.ready_intent_contract())
        self.frame_id = self.service.bootstrap([FRAME])["frame_ids"][0]

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded workflow test requires an evidence-backed research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded workflow fixture to create its explicit research frames.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def saved_capture(self, url: str, title: str, *, discovered_by: list[dict] | None = None,
                       source_metadata: dict | None = None) -> dict:
        content = f"# {title}\n\nSaved source: {url}\n"
        content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        target = self.tmp / "research_drift" / "pages" / f"captured-{content_digest[:16]}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        discovered_by = discovered_by or []
        discovery_providers = list(dict.fromkeys(item["provider"] for item in discovered_by))
        evidence = {
            "url": url,
            "title": title,
            "provider": discovery_providers[0] if discovery_providers else "unknown",
            "discovery_providers": discovery_providers,
            "discovered_by": discovered_by,
            "capture_provider": "anysearch",
            "local_path": str(target.relative_to(self.tmp)).replace("\\", "/"),
            "retrieved_at": "2026-07-29T00:00:00+00:00",
            "capture": {"status": "complete", "method": "anysearch.extract", "character_count": len(content), "limit_chars": 50000},
        }
        evidence.update(source_metadata or {})
        return {
            "evidence": evidence,
            "content_sha256": digest,
        }

    def saved_native_metadata_capture(
        self,
        url: str,
        title: str,
        *,
        provider: str,
        content_kind: str,
        content: str,
        possibly_truncated: bool = False,
        discovered_by: list[dict] | None = None,
        source_metadata: dict | None = None,
    ) -> dict:
        rendered = f"# Provider Metadata Capture\n\nProvider: {provider}\n\n## {content_kind}\n\n{content}\n"
        content_digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        target = self.tmp / "research_drift" / "pages" / f"native-{provider}-{content_digest[:16]}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        discovered_by = discovered_by or []
        discovery_providers = list(dict.fromkeys(item["provider"] for item in discovered_by))
        evidence = {
            "url": url,
            "title": title,
            "provider": provider,
            "discovery_providers": discovery_providers,
            "discovered_by": discovered_by,
            "capture_provider": provider,
            "local_path": str(target.relative_to(self.tmp)).replace("\\", "/"),
            "retrieved_at": "2026-07-29T00:00:00+00:00",
            "capture": {
                "status": "possibly_truncated",
                "method": f"provider_metadata.{provider}",
                "character_count": len(rendered),
                "limit_chars": 10_000,
                "completeness": "metadata_limited",
                "full_text": False,
                "content_kind": content_kind,
                "text_possibly_truncated": possibly_truncated,
            },
        }
        evidence.update(source_metadata or {})
        return {"evidence": evidence, "content_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    @classmethod
    def source_assessment(cls, local_path: str, content_sha256: str) -> dict:
        return {
            "local_path": local_path,
            "content_sha256": content_sha256,
            "relation": "representative",
            "primary": True,
            "quality_components": {key: 0.8 for key in cls.QUALITY_COMPONENTS},
            "assessment_confidence": 0.9,
            "rationale": "The saved page is complete and directly relevant to the bounded topic.",
        }

    @classmethod
    def topic_cluster(cls, topic_key: str, sources: list[dict]) -> dict:
        return {
            "topic_key": topic_key,
            "topic": f"Topic {topic_key}",
            "context_signature": "bounded workflow aggregation context",
            "dedup_rationale": "Group sources by substantive support without discarding a captured page.",
            "sources": sources,
            "representative_local_paths": [sources[0]["local_path"]],
            "confidence_components": {key: 0.8 for key in cls.CONFIDENCE_COMPONENTS},
            "confidence_rationale": "The topic has scoped, auditable saved support.",
            "unresolved": [],
        }

    def aggregation_command(self, frame_id: str, command_id: str = "aggregate-sources-001") -> dict:
        state = self.service.read_state()
        frame = state.data["frames"][frame_id]
        manifest = json.loads((self.tmp / frame["collection"]["source_manifest_path"]).read_text(encoding="utf-8"))
        clusters = [self.topic_cluster(
            f"saved-source-{index}",
            [self.source_assessment(record["evidence"]["local_path"], record["content_sha256"])],
        ) for index, record in enumerate(manifest["records"]) if record.get("status") == "captured"]
        return {
            "command_id": command_id,
            "operation": "aggregate_sources",
            "frame_id": frame_id,
            "aggregator_role": "source_aggregator",
            "clusters": clusters,
            "source_manifest_sha256": frame["collection"]["source_manifest_sha256"],
        }

    @staticmethod
    def discovery_provider_policy() -> dict:
        return {
            "policy": {"max_parallel": 2, "source_capture_limit_per_frame": 24},
            "selected": [{"provider": "anysearch"}, {"provider": "openalex"}],
            "skipped": [],
            "max_parallel": 2,
        }

    def discovery_packet(self) -> dict:
        return {
            "schema": 2,
            "kind": "discovery_batch",
            "records": [
                {
                    "provider": "anysearch", "plan_index": 0, "query": "agent runtime", "status": "ok",
                    "candidates": [{"id": "lead-a", "url": "https://example.com/runtime", "title": "Runtime source"}],
                    "_raw_response": {"content_type": "application/json", "text": '{"jsonrpc":"2.0","result":{}}'},
                },
                {
                    "provider": "openalex", "plan_index": 0, "query": "agent runtime", "status": "ok",
                    "candidates": [{"id": "lead-b", "url": "https://www.example.com/runtime", "title": "Independent source"}],
                    "_raw_response": {"content_type": "application/json", "text": '{"results": []}'},
                },
            ],
            "summary": {"query_count": 1, "provider_count": 2, "success_count": 2,
                        "failure_count": 0, "unavailable_count": 0, "skipped_count": 0},
        }

    def mark_collection_ready(self, frame_id: str) -> None:
        self.service.formulate(frame_id, [{"query": "agent runtime"}])
        request_sha256 = "a" * 64
        discovery = self.tmp / "research_drift" / "discovery" / f"{frame_id}.json"
        manifest = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
        discovery.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        discovery.write_text(json.dumps({"schema": 2, "discovery": {"records": []}}), encoding="utf-8")
        manifest.write_text(json.dumps({
            "schema": 1, "frame_id": frame_id, "request_sha256": request_sha256,
            "records": [], "summary": {"candidate_count": 0, "capture_limit": 1,
                                        "captured_count": 0, "failed_count": 0, "deferred_count": 0},
        }), encoding="utf-8")
        self.service.collection_ready(frame_id, {
            "discovery_path": str(discovery.relative_to(self.tmp)).replace("\\", "/"),
            "source_manifest_path": str(manifest.relative_to(self.tmp)).replace("\\", "/"),
            "request_sha256": request_sha256,
            "summary": {"candidate_count": 0, "capture_limit": 1, "captured_count": 0, "failed_count": 0, "deferred_count": 0},
            "review_roles": ["source_triager", "source_adversary"],
        })

    def test_workflow_command_is_idempotent(self):
        command = {
            "command_id": "formulate-001",
            "operation": "formulate",
            "frame_id": self.frame_id,
            "plan": [{"query": "agent runtime"}],
        }
        first = self.service.execute(command)
        second = self.service.execute(command)
        self.assertFalse(first["deduplicated"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(self.service.status()["frame_states"], {"acquiring": 1})

    def test_langgraph_does_not_spawn_a_worker_before_collection(self):
        graph = build_research_graph(InMemorySaver(), self.service)
        config = {"configurable": {"thread_id": "research-test"}}
        initial = graph.invoke({}, config)
        self.assertNotIn("__interrupt__", initial)
        self.assertEqual(initial["batch"]["tasks"], [])
        self.assertEqual(initial["batch"]["coordinator_tasks"][0]["role"], "coordinator")
        self.assertEqual(initial["batch"]["coordinator_tasks"][0]["kind"], "formulate")
        self.assertEqual(self.service.status()["frame_states"], {"open": 1})

    def test_langgraph_interrupt_resumes_saved_source_review_through_service(self):
        self.mark_collection_ready(self.frame_id)
        graph = build_research_graph(InMemorySaver(), self.service)
        config = {"configurable": {"thread_id": "review-test"}}
        paused = graph.invoke({}, config)
        self.assertIn("__interrupt__", paused)
        aggregation_tasks = paused["__interrupt__"][0].value["batch"]["tasks"]
        self.assertEqual([task["role"] for task in aggregation_tasks], ["source_aggregator"])
        resumed = graph.invoke(Command(resume=[self.aggregation_command(self.frame_id)]), config)
        self.assertNotIn("__interrupt__", resumed)
        self.assertEqual(self.service.status()["frame_states"], {"reviewing": 1})

        paused = graph.invoke({}, config)
        self.assertIn("__interrupt__", paused)
        task_roles = {task["reviewer_role"] for task in paused["__interrupt__"][0].value["batch"]["tasks"]}
        self.assertEqual(task_roles, {"source_triager", "source_adversary"})
        resumed = graph.invoke(Command(resume=[
            {"command_id": "triage-review-001", "operation": "evidence", "frame_id": self.frame_id,
             "reviewer_role": "source_triager", "evidence": []},
            {"command_id": "adversary-review-001", "operation": "evidence", "frame_id": self.frame_id,
             "reviewer_role": "source_adversary", "evidence": []},
        ]), config)
        self.assertNotIn("__interrupt__", resumed)
        self.assertEqual(self.service.status()["frame_states"], {"extracting": 1})

    def test_runner_rejects_an_ephemeral_default(self):
        with self.assertRaisesRegex(ValueError, "persistent"):
            build_research_graph(None, self.service)

    def test_orchestrator_archives_all_search_raw_responses_before_emitting_review_workers(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        orchestrator = ResearchOrchestrator(self.service)
        before = orchestrator.plan()
        self.assertEqual(before["tasks"], [])
        self.assertEqual(before["coordinator_tasks"][0]["kind"], "discover-and-materialize")
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()) as run, \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture) as capture:
            result = orchestrator.discover()
        self.assertEqual(result["results"][0]["status"], "executed")
        run.assert_called_once()
        self.assertEqual(capture.call_count, 2)
        discovery_path = self.tmp / result["results"][0]["path"]
        payload = json.loads(discovery_path.read_text(encoding="utf-8"))
        raw_paths = [record["raw_response"]["path"] for record in payload["discovery"]["records"]]
        self.assertTrue(all((self.tmp / path).is_file() for path in raw_paths))
        source_manifest = self.tmp / result["results"][0]["source_materialisation"]["path"]
        source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        self.assertEqual(source_payload["summary"]["captured_count"], 2)
        self.assertTrue(all((self.tmp / item["evidence"]["local_path"]).is_file() for item in source_payload["records"]))
        after = orchestrator.plan()
        self.assertEqual({task["role"] for task in after["tasks"]}, {"source_aggregator"})
        self.assertEqual(after["coordinator_tasks"], [])
        self.service.execute(self.aggregation_command(self.frame_id))
        reviewers = orchestrator.plan()
        self.assertEqual({task["role"] for task in reviewers["tasks"]}, {"source_triager", "source_adversary"})

    def test_no_reviewers_are_planned_before_source_aggregation_completes(self):
        self.mark_collection_ready(self.frame_id)
        orchestrator = ResearchOrchestrator(self.service)
        before = orchestrator.plan()
        self.assertEqual({task["role"] for task in before["tasks"]}, {"source_aggregator"})
        self.assertNotIn("source_triager", {task["role"] for task in before["tasks"]})
        self.assertNotIn("source_adversary", {task["role"] for task in before["tasks"]})
        self.service.execute(self.aggregation_command(self.frame_id, "aggregate-before-review"))
        after = orchestrator.plan()
        self.assertEqual({task["role"] for task in after["tasks"]}, {"source_triager", "source_adversary"})

    def test_workflow_cannot_freeze_while_source_aggregation_is_pending(self):
        self.mark_collection_ready(self.frame_id)
        with self.assertRaisesRegex(ValueError, "active frames remain"):
            self.service.execute({"command_id": "freeze-before-aggregation", "operation": "freeze"})

    def test_orchestrator_schedules_decision_synthesis_before_freeze(self):
        state = self.service.read_state()
        state.data["intent_contract"]["contract"]["decision_questions"] = [{
            "id": "adoption", "question": "Should the bounded change be approved?",
            "why_it_matters": "It determines the implementation commitment.", "impact": "high",
            "deliverable_ids": ["test-fixture"],
        }]
        state.data["decision_synthesis"] = {
            "schema": 1, "status": "pending", "synthesis": None, "sha256": None,
        }
        state.data["frames"][self.frame_id]["state"] = "gap_user_input"
        state.data["frames"][self.frame_id]["return"] = {"summary": "needs a user input", "confidence": 0.0}
        state.save()
        batch = ResearchOrchestrator(self.service).plan()
        self.assertEqual([task["role"] for task in batch["tasks"]], ["decision_synthesizer"])
        task = batch["tasks"][0]
        self.assertEqual(task["allowed_operation"], "synthesize_decision")
        self.assertEqual(task["synthesizer_role"], "decision_synthesizer")
        result = self.service.execute({
            "command_id": "decision-synthesis", "operation": "synthesize_decision",
            "synthesizer_role": "decision_synthesizer",
            "synthesis": {
                "overall_status": "need_user_input", "recommendation": "defer",
                "summary": "The adoption decision needs a missing input.",
                "question_assessments": [{
                    "decision_question_id": "adoption", "status": "need_user_input",
                    "conclusion": "No baseline requirement is recorded.",
                    "supporting_cognition_ids": [], "refuting_cognition_ids": [], "gap_ids": [],
                    "user_questions": ["Which baseline should govern the decision?"],
                    "conditions_to_change": [], "action": "Ask for the baseline before adoption.",
                }], "parameter_provenance": [],
            },
        })
        self.assertFalse(result["deduplicated"])
        after = ResearchOrchestrator(self.service).plan()
        self.assertEqual(after["tasks"][0]["kind"], "freeze")

    def test_source_manifest_separates_discovery_origins_from_capture_transport(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        orchestrator = ResearchOrchestrator(self.service)
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()), \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture):
            result = orchestrator.discover()
        manifest_path = self.tmp / result["results"][0]["source_materialisation"]["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], 2)
        captured = [item for item in manifest["records"] if item["status"] == "captured"]
        self.assertEqual(captured[0]["evidence"]["discovery_providers"], ["anysearch"])
        self.assertEqual(captured[1]["evidence"]["discovery_providers"], ["openalex"])
        self.assertEqual(captured[0]["evidence"]["capture_provider"], "anysearch")
        self.assertEqual(manifest["summary"]["origin_coverage"], {
            "candidate_origins": {"anysearch": 1, "openalex": 1},
            "captured_origins": {"anysearch": 1, "openalex": 1},
            "failed_origins": {},
            "deferred_origins": {},
            "capture_transports": {"anysearch": 2},
        })
        collection_summary = self.service.read_state().data["frames"][self.frame_id]["collection"]["summary"]
        self.assertEqual(collection_summary["origin_coverage"], manifest["summary"]["origin_coverage"])

    def test_source_materialisation_uses_native_metadata_alongside_page_extraction(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        packet = self.discovery_packet()
        native_text = " ".join(["bounded" for _ in range(40)])
        packet["records"][1]["candidates"][0]["native_metadata"] = {
            "provider": "openalex",
            "url": "https://openalex.org/W42",
            "title": "OpenAlex native record",
            "content_kind": "abstract",
            "text": native_text,
            "possibly_truncated": False,
            "source_metadata": {"published_at": "2025-01-02"},
        }
        orchestrator = ResearchOrchestrator(self.service)
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=packet), \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture) as page_capture, \
                mock.patch(
                    "research_orchestrator.source_acquirer.acquire_provider_metadata",
                    side_effect=self.saved_native_metadata_capture,
                ) as metadata_capture:
            result = orchestrator.discover()
        page_capture.assert_called_once()
        metadata_capture.assert_called_once()
        self.assertEqual(metadata_capture.call_args.kwargs["provider"], "openalex")
        self.assertEqual(metadata_capture.call_args.kwargs["content"], native_text)
        manifest_path = self.tmp / result["results"][0]["source_materialisation"]["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        transports = {
            item["evidence"]["capture_provider"]
            for item in manifest["records"] if item["status"] == "captured"
        }
        self.assertEqual(transports, {"anysearch", "openalex"})
        self.assertEqual(manifest["summary"]["origin_coverage"]["capture_transports"], {
            "anysearch": 1,
            "openalex": 1,
        })
        native_record = next(
            item for item in manifest["records"]
            if item.get("evidence", {}).get("capture_provider") == "openalex"
        )
        self.assertEqual(native_record["evidence"]["capture"]["completeness"], "metadata_limited")
        self.assertFalse(native_record["evidence"]["capture"]["full_text"])

    def test_short_native_metadata_falls_back_to_anysearch_page_extraction(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        packet = self.discovery_packet()
        packet["records"] = [packet["records"][1]]
        packet["records"][0]["candidates"][0]["native_metadata"] = {
            "provider": "openalex",
            "url": "https://openalex.org/W42",
            "title": "OpenAlex native record",
            "content_kind": "abstract",
            "text": "Too short to replace a page extraction.",
            "possibly_truncated": False,
            "source_metadata": {},
        }
        packet["summary"] = {
            "query_count": 1, "provider_count": 1, "success_count": 1,
            "failure_count": 0, "unavailable_count": 0, "skipped_count": 0,
        }
        policy = {
            "policy": {"max_parallel": 1, "source_capture_limit_per_frame": 24},
            "selected": [{"provider": "openalex"}], "skipped": [], "max_parallel": 1,
        }
        with mock.patch("research_orchestrator.providers.eligible", return_value=policy), \
                mock.patch("research_orchestrator.run_plan", return_value=packet), \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture) as page_capture, \
                mock.patch("research_orchestrator.source_acquirer.acquire_provider_metadata") as metadata_capture:
            result = ResearchOrchestrator(self.service).discover()
        metadata_capture.assert_not_called()
        page_capture.assert_called_once()
        manifest_path = self.tmp / result["results"][0]["source_materialisation"]["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        captured = [item for item in manifest["records"] if item["status"] == "captured"]
        self.assertEqual(captured[0]["evidence"]["capture_provider"], "anysearch")
        self.assertEqual(captured[0]["evidence"]["discovery_providers"], ["openalex"])

    def test_discovery_cache_is_reused_only_after_complete_archive_and_manifest(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        orchestrator = ResearchOrchestrator(self.service)
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()) as run, \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture):
            result = orchestrator.discover()
        self.assertEqual(result["results"][0]["status"], "executed")
        run.assert_called_once()
        # Simulate recovery after the durable files were written but before a
        # subsequent scheduler turn. The cached artifacts must avoid a rerun.
        state = self.service.read_state()
        state.data["frames"][self.frame_id]["state"] = "acquiring"
        state.save()
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan") as run:
            cached = orchestrator.discover()
        self.assertEqual(cached["results"][0]["status"], "cached")
        run.assert_not_called()

    def test_missing_raw_archive_invalidates_the_discovery_cache(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        orchestrator = ResearchOrchestrator(self.service)
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()), \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture):
            first = orchestrator.discover()
        discovery = json.loads((self.tmp / first["results"][0]["path"]).read_text(encoding="utf-8"))
        raw_path = self.tmp / discovery["discovery"]["records"][0]["raw_response"]["path"]
        raw_path.unlink()
        state = self.service.read_state()
        state.data["frames"][self.frame_id]["state"] = "acquiring"
        state.save()
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()) as run, \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture):
            recovered = orchestrator.discover()
        self.assertEqual(recovered["results"][0]["status"], "executed")
        run.assert_called_once()

    def test_missing_saved_page_invalidates_only_the_source_manifest_cache(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        orchestrator = ResearchOrchestrator(self.service)
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan", return_value=self.discovery_packet()), \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture):
            first = orchestrator.discover()
        manifest_path = self.tmp / first["results"][0]["source_materialisation"]["path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        page_path = self.tmp / manifest["records"][0]["evidence"]["local_path"]
        page_path.unlink()
        state = self.service.read_state()
        state.data["frames"][self.frame_id]["state"] = "acquiring"
        state.save()
        with mock.patch("research_orchestrator.providers.eligible", return_value=self.discovery_provider_policy()), \
                mock.patch("research_orchestrator.run_plan") as run, \
                mock.patch("research_orchestrator.source_acquirer.acquire_anysearch", side_effect=self.saved_capture) as capture:
            recovered = orchestrator.discover()
        self.assertEqual(recovered["results"][0]["status"], "cached")
        self.assertEqual(recovered["results"][0]["source_materialisation"]["status"], "executed")
        run.assert_not_called()
        self.assertEqual(capture.call_count, 2)

    def test_collection_does_not_advance_when_no_executable_provider_is_eligible(self):
        self.service.formulate(self.frame_id, [{"query": "agent runtime"}])
        policy = {"policy": {"max_parallel": 1, "source_capture_limit_per_frame": 24},
                  "selected": [], "skipped": [{"provider": "ddg", "reasons": ["adapter_unavailable"]}],
                  "max_parallel": 1}
        with mock.patch("research_orchestrator.providers.eligible", return_value=policy):
            with self.assertRaisesRegex(ValueError, "no eligible executable discovery providers"):
                ResearchOrchestrator(self.service).discover()
        self.assertEqual(self.service.status()["frame_states"], {"acquiring": 1})

    def test_langgraph_fans_out_to_injected_worker_executor(self):
        self.mark_collection_ready(self.frame_id)

        def executor(task):
            if task["role"] == "source_aggregator":
                return self.aggregation_command(task["frame_id"], "worker-aggregate-001")
            self.assertIn(task["role"], {"source_triager", "source_adversary"})
            return {"command_id": f"worker-{task['reviewer_role']}-001", "operation": "evidence",
                    "frame_id": task["frame_id"], "reviewer_role": task["reviewer_role"], "evidence": []}

        graph = build_research_graph(InMemorySaver(), self.service, executor)
        graph.invoke({}, {"configurable": {"thread_id": "fanout-test"}})
        self.assertEqual(self.service.status()["frame_states"], {"reviewing": 1})
        graph.invoke({"pending_tasks": None}, {"configurable": {"thread_id": "fanout-test"}})
        self.assertEqual(self.service.status()["frame_states"], {"extracting": 1})

    def test_runtime_config_preserves_thread_id_and_caps_concurrency(self):
        config = research_graph_config({"configurable": {"thread_id": "cap-test", "max_concurrency": 9}}, 3)
        self.assertEqual(config["configurable"], {"thread_id": "cap-test", "max_concurrency": 3})
        default_config = research_graph_config({"configurable": {"thread_id": "writer-batch"}})
        self.assertEqual(default_config["configurable"], {"thread_id": "writer-batch"})
        with self.assertRaisesRegex(ValueError, "positive integer"):
            research_graph_config({"configurable": {"max_concurrency": 0}}, 3)

    def test_langgraph_batches_dynamic_workers_to_max_parallel(self):
        frames = []
        for index in range(3):
            frame = dict(FRAME)
            frame["focus"] = f"runtime capability {index}"
            frame["information_gap"] = f"primitive {index}"
            frames.append(frame)
        frame_ids = self.service.bootstrap(frames)["frame_ids"]
        for frame_id in [self.frame_id, *frame_ids]:
            self.mark_collection_ready(frame_id)
        active = 0
        peak = 0
        lock = threading.Lock()

        def executor(task):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            if task["role"] == "source_aggregator":
                return self.aggregation_command(task["frame_id"], f"batched-{task['frame_id']}-aggregate")
            return {"command_id": f"batched-{task['frame_id']}-{task['reviewer_role']}", "operation": "evidence",
                    "frame_id": task["frame_id"], "reviewer_role": task["reviewer_role"], "evidence": []}

        policy = {"policy": {"max_parallel": 1}, "selected": [], "skipped": [], "max_parallel": 1}
        graph = build_research_graph(InMemorySaver(), self.service, executor)
        with mock.patch("research_orchestrator.providers.eligible", return_value=policy):
            invoke_research_graph(graph, {}, {"configurable": {"thread_id": "batch-cap"}}, max_parallel=1)
            self.assertEqual(self.service.status()["frame_states"], {"reviewing": 4})
            invoke_research_graph(graph, {"pending_tasks": None}, {"configurable": {"thread_id": "batch-cap"}}, max_parallel=1)
        self.assertEqual(peak, 1)
        self.assertEqual(self.service.status()["frame_states"], {"extracting": 4})

    def test_orchestrator_creates_a_dedicated_frozen_qa_task(self):
        packet = {"status": "retrieved", "snapshot_id": "frozen-unit", "question": "What changed?",
                  "reference_time": "2026-07-29T00:00:00+00:00", "frozen_at": "2026-07-29T01:00:00+00:00",
                  "evidence_packets": [{"chunk_id": "c_abc", "source_path": "research_snapshots/frozen-unit/pages/a.md"}]}
        with mock.patch("qa.ask", return_value=packet) as ask:
            batch = ResearchOrchestrator(self.service).plan(snapshot="frozen-unit", question="What changed?")
        ask.assert_called_once_with("frozen-unit", "What changed?", 8)
        task = batch["tasks"][0]
        self.assertEqual(task["role"], "qa")
        self.assertEqual(task["kind"], "answer-question")
        self.assertEqual(task["evidence_packets"], packet["evidence_packets"])

    def test_orchestrator_rejects_live_qa(self):
        with self.assertRaisesRegex(ValueError, "frozen snapshot"):
            ResearchOrchestrator(self.service).plan(question="What changed?")


if __name__ == "__main__":
    unittest.main(verbosity=2)
