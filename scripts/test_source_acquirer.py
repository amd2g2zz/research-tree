"""Tests for the non-mutating AnySearch source acquisition boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import anysearch_client  # noqa: E402
import source_acquirer  # noqa: E402
from research_service import ResearchService  # noqa: E402


FRAME = {
    "focus": "source capture", "information_gap": "which source is authoritative",
    "discriminator": "saved public primary source", "expected_update": "support one claim",
    "evidence_requirement": "saved source page",
}


class SourceAcquirerTests(unittest.TestCase):
    QUALITY_COMPONENTS = (
        "authority", "directness", "traceability", "temporal_fit",
        "capture_completeness", "independence",
    )
    CONFIDENCE_COMPONENTS = (
        "source_quality", "corroboration", "independence",
        "temporal_coherence", "scope_match",
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt-acquirer-"))
        self.env = mock.patch.dict(os.environ, {"RESEARCH_WORKSPACE": str(self.tmp)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def ready_intent_contract() -> dict:
        return {
            "status": "ready",
            "summary": "The bounded test request requires a source-capture research deliverable.",
            "deliverables": [{
                "id": "test-fixture", "kind": "test_fixture", "requires_research": False,
                "description": "Authorize the bounded source-capture fixture to create its explicit research frame.",
            }],
            "research_questions": [], "design_requirements": [], "writing_requirements": [],
            "acceptance_criteria": [], "assumptions": [], "other_constraints": [],
            "user_materials": [], "clarifying_questions": [], "research_frames": [],
        }

    def initialize_service(self, service: ResearchService) -> None:
        service.initialize("Inspect source capture", [], "2026-07-29T00:00:00+00:00")
        service.analyze_intent(self.ready_intent_contract())

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
            "rationale": "The captured page is complete and directly relevant to this bounded topic.",
        }

    @classmethod
    def topic_cluster(cls, topic_key: str, sources: list[dict], representatives: list[str] | None = None) -> dict:
        return {
            "topic_key": topic_key,
            "topic": f"Topic {topic_key}",
            "context_signature": "bounded source-acquisition test context",
            "dedup_rationale": "Group substantive support without dropping a captured source.",
            "sources": sources,
            "representative_local_paths": representatives or [sources[0]["local_path"]],
            "confidence_components": {key: 0.8 for key in cls.CONFIDENCE_COMPONENTS},
            "confidence_rationale": "The captured sources provide scoped support with auditable provenance.",
            "unresolved": [],
        }

    def aggregate_saved_sources(self, service: ResearchService, frame_id: str,
                                clusters: list[dict] | None = None,
                                *, source_manifest_sha256: str | None = None) -> dict:
        state = service.read_state()
        frame = state.data["frames"][frame_id]
        manifest = json.loads((self.tmp / frame["collection"]["source_manifest_path"]).read_text(encoding="utf-8"))
        if clusters is None:
            clusters = [self.topic_cluster(
                f"saved-source-{index}",
                [self.source_assessment(record["evidence"]["local_path"], record["content_sha256"])],
            ) for index, record in enumerate(manifest["records"]) if record.get("status") == "captured"]
        return service.aggregate_sources(
            frame_id,
            clusters,
            source_manifest_sha256 or frame["collection"]["source_manifest_sha256"],
        )

    def begin_saved_source_review(self, service: ResearchService, frame_id: str, proposals: list[dict],
                                  *, aggregate: bool = True) -> None:
        discovery = self.tmp / "research_drift" / "discovery" / f"{frame_id}.json"
        manifest = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
        discovery.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        discovery.write_text("{}", encoding="utf-8")
        records = [{"status": "captured", "evidence": dict(proposal),
                    "content_sha256": hashlib.sha256((self.tmp / proposal["local_path"]).read_bytes()).hexdigest()}
                   for proposal in proposals]
        summary = {"candidate_count": len(records), "capture_limit": max(1, len(records)),
                   "captured_count": len(records), "failed_count": 0, "deferred_count": 0}
        manifest.write_text(json.dumps({"schema": 1, "frame_id": frame_id, "request_sha256": "a" * 64,
                                        "records": records, "summary": summary}), encoding="utf-8")
        service.collection_ready(frame_id, {
            "discovery_path": str(discovery.relative_to(self.tmp)).replace("\\", "/"),
            "source_manifest_path": str(manifest.relative_to(self.tmp)).replace("\\", "/"),
            "request_sha256": "a" * 64,
            "summary": summary,
            "review_roles": ["source_triager", "source_adversary"],
        })
        if aggregate:
            self.aggregate_saved_sources(service, frame_id)

    def test_acquirer_saves_only_a_deterministic_page_and_returns_evidence_package(self):
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="# Source\n\nCaptured text") as extract:
            result = source_acquirer.acquire_anysearch("https://example.com/source", " Example source ")
        extract.assert_called_once_with("https://example.com/source")
        evidence = result["evidence"]
        path = self.tmp / evidence["local_path"]
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), "# Source\n\nCaptured text")
        self.assertEqual(evidence["provider"], "unknown")
        self.assertEqual(evidence["discovery_providers"], [])
        self.assertEqual(evidence["capture_provider"], "anysearch")
        self.assertEqual(evidence["title"], "Example source")
        self.assertEqual(evidence["capture"]["status"], "complete")
        self.assertFalse((self.tmp / "research_drift" / "research_state.json").exists())

    def test_acquirer_preserves_discovery_origins_and_temporal_metadata(self):
        origins = [
            {"provider": "openalex", "plan_index": 0, "candidate_id": "W42", "candidate_url": "https://openalex.org/W42"},
            {"provider": "crossref", "plan_index": 1, "candidate_id": "10.1/example", "candidate_url": "https://doi.org/10.1/example"},
        ]
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="# Source\n\nCaptured text"):
            evidence = source_acquirer.acquire_anysearch(
                "https://example.com/source",
                "Example source",
                discovered_by=origins,
                source_metadata={"published_at": "2025-02-03", "updated_at": "2026-01-01T00:00:00Z"},
            )["evidence"]
        self.assertEqual(evidence["provider"], "openalex")
        self.assertEqual(evidence["discovery_providers"], ["openalex", "crossref"])
        self.assertEqual(evidence["discovered_by"], origins)
        self.assertEqual(evidence["capture_provider"], "anysearch")
        self.assertEqual(evidence["published_at"], "2025-02-03")
        self.assertEqual(evidence["updated_at"], "2026-01-01T00:00:00Z")

    def test_provider_metadata_capture_is_deterministic_and_explicitly_not_full_text(self):
        origins = [{
            "provider": "openalex", "plan_index": 0, "candidate_id": "W42",
            "candidate_url": "https://openalex.org/W42",
        }]
        content = " ".join([
            "This normalized abstract describes a bounded experimental method and its measured outcomes.",
            "It is provider metadata rather than a retrieved article body.",
        ])
        first = source_acquirer.acquire_provider_metadata(
            "https://openalex.org/W42",
            "Native OpenAlex record",
            provider="openalex",
            content_kind="abstract",
            content=content,
            discovered_by=origins,
            source_metadata={"published_at": "2025-02-03"},
        )
        second = source_acquirer.acquire_provider_metadata(
            "https://openalex.org/W42",
            "Native OpenAlex record",
            provider="openalex",
            content_kind="abstract",
            content=content,
            discovered_by=origins,
            source_metadata={"published_at": "2025-02-03"},
        )
        evidence = first["evidence"]
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        self.assertEqual(evidence["provider"], "openalex")
        self.assertEqual(evidence["capture_provider"], "openalex")
        self.assertEqual(evidence["capture"]["method"], "provider_metadata.openalex")
        self.assertEqual(evidence["capture"]["status"], "possibly_truncated")
        self.assertEqual(evidence["capture"]["completeness"], "metadata_limited")
        self.assertFalse(evidence["capture"]["full_text"])
        page = (self.tmp / first["path"]).read_text(encoding="utf-8")
        self.assertIn("normalized provider metadata only, not full text", page)
        self.assertIn(content, page)

    def test_acquirer_rejects_recognized_extractor_error_content(self):
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="extract_upstream_error\nupstream returned error: HTTP 403"):
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "extract_upstream_error"):
                source_acquirer.acquire_anysearch("https://example.com/source")

    def test_acquirer_marks_the_extractor_boundary_without_truncating(self):
        with mock.patch(
            "source_acquirer.anysearch_client.extract", return_value="x" * anysearch_client.MAX_EXTRACTED_TEXT_CHARS
        ):
            result = source_acquirer.acquire_anysearch("https://example.com/source")
        self.assertEqual(result["evidence"]["capture"]["status"], "possibly_truncated")
        self.assertEqual(result["evidence"]["capture"]["character_count"], anysearch_client.MAX_EXTRACTED_TEXT_CHARS)

    def test_unsafe_url_is_rejected_before_any_network_client_call(self):
        with mock.patch("source_acquirer.anysearch_client.extract") as extract:
            with self.assertRaisesRegex(anysearch_client.AnySearchRequestError, "invalid_extract_url"):
                source_acquirer.acquire_anysearch("http://127.0.0.1/private")
        extract.assert_not_called()

    def test_capture_metadata_survives_the_service_evidence_boundary(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="captured evidence"):
            proposal = source_acquirer.acquire_anysearch("https://example.com/source")["evidence"]
        self.begin_saved_source_review(service, frame_id, [proposal])
        service.add_evidence(frame_id, [proposal], "source_triager")
        service.add_evidence(frame_id, [], "source_adversary")
        evidence_id = service.read_state().data["frames"][frame_id]["evidence_ids"][0]
        persisted = service.read_state().data["evidence"][evidence_id]
        self.assertEqual(persisted["capture"], proposal["capture"])
        self.assertEqual(persisted["capture_provider"], "anysearch")
        self.assertEqual(persisted["discovery_providers"], [])

    def test_metadata_limited_capture_details_survive_the_service_evidence_boundary(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        origin = [{
            "provider": "openalex", "plan_index": 0, "candidate_id": "W42",
            "candidate_url": "https://openalex.org/W42",
        }]
        proposal = source_acquirer.acquire_provider_metadata(
            "https://openalex.org/W42", "Bounded metadata record", provider="openalex",
            content_kind="abstract",
            content="A sufficiently detailed normalized abstract for provenance-bound service persistence.",
            discovered_by=origin, source_metadata={"published_at": "2025-02-03"},
        )["evidence"]
        self.begin_saved_source_review(service, frame_id, [proposal])
        service.add_evidence(frame_id, [proposal], "source_triager")
        service.add_evidence(frame_id, [], "source_adversary")
        evidence_id = service.read_state().data["frames"][frame_id]["evidence_ids"][0]
        persisted = service.read_state().data["evidence"][evidence_id]
        self.assertEqual(persisted["capture"]["completeness"], "metadata_limited")
        self.assertFalse(persisted["capture"]["full_text"])
        self.assertEqual(persisted["capture"]["content_kind"], "abstract")

    def test_service_rejects_evidence_before_collection_review(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with self.assertRaisesRegex(ValueError, "reviewing frame after saved-source collection"):
            service.add_evidence(frame_id, [], "source_triager")

    def test_review_can_select_only_sources_in_its_current_manifest(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="captured evidence"):
            proposal = source_acquirer.acquire_anysearch("https://example.com/source")["evidence"]
        unrelated = self.tmp / "research_drift" / "pages" / "unrelated.md"
        unrelated.write_text("not in this collection", encoding="utf-8")
        self.begin_saved_source_review(service, frame_id, [proposal])
        with self.assertRaisesRegex(ValueError, "current source manifest"):
            service.add_evidence(frame_id, [{"local_path": "research_drift/pages/unrelated.md"}], "source_triager")

    def test_review_rejects_a_manifest_from_a_different_collection_request(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="captured evidence"):
            proposal = source_acquirer.acquire_anysearch("https://example.com/source")["evidence"]
        self.begin_saved_source_review(service, frame_id, [proposal])
        manifest_path = self.tmp / "research_drift" / "sources" / f"{frame_id}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["request_sha256"] = "b" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source manifest no longer matches its collection hash"):
            service.add_evidence(frame_id, [proposal], "source_triager")

    def test_low_quality_nonrepresentative_selection_requires_an_override(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with mock.patch("source_acquirer.anysearch_client.extract", side_effect=["representative evidence", "weak alternative evidence"]):
            representative = source_acquirer.acquire_anysearch("https://example.com/representative")["evidence"]
            weak = source_acquirer.acquire_anysearch("https://example.com/weak")["evidence"]
        self.begin_saved_source_review(service, frame_id, [representative, weak], aggregate=False)
        state = service.read_state()
        manifest = json.loads((self.tmp / state.data["frames"][frame_id]["collection"]["source_manifest_path"]).read_text(encoding="utf-8"))
        hashes = {record["evidence"]["local_path"]: record["content_sha256"] for record in manifest["records"]}
        cluster = self.topic_cluster(
            "source-selection",
            [
                self.source_assessment(representative["local_path"], hashes[representative["local_path"]]),
                self.source_assessment(
                    weak["local_path"], hashes[weak["local_path"]], relation="corroborating", quality=0.3,
                ),
            ],
            [representative["local_path"]],
        )
        self.aggregate_saved_sources(service, frame_id, [cluster])
        with self.assertRaisesRegex(ValueError, "requires selection_override_rationale"):
            service.add_evidence(frame_id, [weak], "source_triager")
        selected = dict(weak, selection_override_rationale="Retain this weak, non-representative counterexample as a documented limitation.")
        result = service.add_evidence(frame_id, [selected], "source_triager")
        evidence = service.read_state().data["evidence"][result["evidence_ids"][0]]
        self.assertEqual(evidence["aggregation_assessment"]["quality_score"], 0.3)
        self.assertFalse(evidence["aggregation_assessment"]["representative"])
        self.assertEqual(
            evidence["aggregation_assessment"]["selection_override_rationale"],
            selected["selection_override_rationale"],
        )

    def test_extraction_caps_claim_confidence_from_saved_source_assessment(self):
        service = ResearchService()
        self.initialize_service(service)
        frame_id = service.bootstrap([FRAME])["frame_ids"][0]
        service.formulate(frame_id, [{"query": "source capture"}])
        with mock.patch("source_acquirer.anysearch_client.extract", return_value="weak but saved evidence"):
            proposal = source_acquirer.acquire_anysearch("https://example.com/weak") ["evidence"]
        self.begin_saved_source_review(service, frame_id, [proposal], aggregate=False)
        state = service.read_state()
        manifest = json.loads((self.tmp / state.data["frames"][frame_id]["collection"]["source_manifest_path"]).read_text(encoding="utf-8"))
        content_sha256 = manifest["records"][0]["content_sha256"]
        cluster = self.topic_cluster(
            "weak-source",
            [self.source_assessment(proposal["local_path"], content_sha256, quality=0.2)],
        )
        cluster["confidence_components"] = {key: 0.4 for key in self.CONFIDENCE_COMPONENTS}
        self.aggregate_saved_sources(service, frame_id, [cluster])
        selected = dict(
            proposal,
            selection_override_rationale="Keep the weak saved source so the resulting claim is explicitly confidence-capped.",
        )
        evidence_id = service.add_evidence(frame_id, [selected], "source_triager")["evidence_ids"][0]
        service.add_evidence(frame_id, [], "source_adversary")

        result = service.extract(frame_id, [{
            "claim": "The saved page supports a narrowly qualified observation.",
            "context_signature": "bounded weak-source test",
            "evidence_time": "2026-07-29T00:00:00+00:00",
            "confidence": 0.99,
            "source_spans": [{"evidence_id": evidence_id, "locator": "p:1"}],
        }], [])
        cognition = service.read_state().data["cognitions"][result["cognition_ids"][0]]
        self.assertEqual(cognition["confidence_requested"], 0.99)
        self.assertEqual(cognition["confidence_cap"], 0.385)
        self.assertEqual(cognition["confidence"], 0.385)
        self.assertEqual(cognition["evidence_assessment"]["clusters"][0]["quality_score"], 0.2)
        self.assertEqual(cognition["evidence_assessment"]["clusters"][0]["cluster_confidence"], 0.4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
