from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_tree.claims import Claim, ClaimAdmissionEvaluator, ClaimGrounding, ClaimState
from research_tree.content_store import ContentAddressedStore
from research_tree.evidence import EvidenceAnchor, EvidenceArtifact, EvidenceRepository, EvidenceResolver
from research_tree.run_ledger import RunLedger
from research_tree.search_portfolio import MethodExecutionOutcome, assess_acquisition_batch


def _claim() -> Claim:
    return Claim(
        claim_id="claim-release-version",
        subject="research-tree",
        predicate="ships",
        value="version 2",
        polarity="positive",
        scope="public release",
        version="2",
        time_range="2026-08",
        conditions=("default distribution",),
    )


@dataclass
class _EvidenceContext:
    ledger: RunLedger
    store: ContentAddressedStore
    resolver: EvidenceResolver


def _context(tmp_path: Path) -> _EvidenceContext:
    ledger = RunLedger(tmp_path / "ledger")
    ledger.initialize()
    ledger.create_run("claim-run")
    store = ContentAddressedStore(tmp_path / "content")
    return _EvidenceContext(ledger, store, EvidenceResolver.from_ledger(ledger, store))


def _grounding(
    context: _EvidenceContext,
    grounding_id: str,
    *,
    upstream_id: str,
    extract_text: str = "research-tree ships version 2 in the public release",
    version: str = "2",
    content_fingerprint: str | None = None,
) -> ClaimGrounding:
    content = context.store.ingest(extract_text.encode(), "text/plain")
    evidence = EvidenceArtifact(
        evidence_id=f"evidence-{grounding_id}",
        run_id="claim-run",
        revision=1,
        media_type="text/plain",
        locator={"url": f"https://example.invalid/{grounding_id}"},
        content_digest=content.digest,
        size_bytes=content.byte_size,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        acquisition_method="fixture",
        provenance_group=upstream_id,
        applicability="direct support",
        confidence="high",
        limitations=(),
        status="active",
        extractor_version="claim-fixture-v1",
        evidence_class="source",
        metadata={
            "canonical_upstream_id": upstream_id,
            "content_fingerprint": content_fingerprint or content.digest,
            "claim_version": version,
            "claim_time_range": "2026-08",
            "claim_scope": "public release",
            "claim_conditions": ["default distribution"],
        },
    )
    reference = EvidenceRepository(context.ledger, context.store).record(
        evidence,
        content,
        expected_run_revision=context.ledger.get_revision("claim-run"),
    )
    anchor = EvidenceAnchor(
        artifact_ref=reference,
        artifact_digest=content.digest,
        artifact_revision=reference.revision,
        selector_type="line",
        selector_value={"start": 1, "end": 1},
        extractor_version="claim-fixture-v1",
        applicability="direct support",
        confidence="high",
        limitations=(),
    )
    return ClaimGrounding(
        grounding_id=grounding_id,
        claim_id="claim-release-version",
        anchor=anchor.to_dict(),
    )


def _outcome() -> MethodExecutionOutcome:
    return MethodExecutionOutcome(
        outcome_id="outcome-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        method_id="web-search",
        provider_id="provider-a",
        failure_boundary="provider-a-boundary",
        selection_reason="primary-coverage",
        disposition="captured",
        query_refs=("query-1",),
        capture_refs=("capture-grounding-1",),
        coverage="complete",
        novelty="new",
        source_quality="high",
        source_depth="full-source",
        unresolved_decision_risk="low",
    )


def test_same_upstream_through_two_providers_remains_isolated(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assessment = ClaimAdmissionEvaluator(context.resolver).assess(
        _claim(),
        (
            _grounding(context, "one", upstream_id="release-note-2"),
            _grounding(context, "two", upstream_id="release-note-2"),
        ),
    )

    assert assessment.state is ClaimState.ISOLATED
    assert assessment.provenance_clusters == ("release-note-2",)
    assert assessment.decision_authority is False


def test_independent_entailing_sources_corroborate_claim(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assessment = ClaimAdmissionEvaluator(context.resolver).assess(
        _claim(),
        (
            _grounding(context, "official", upstream_id="release-note-2"),
            _grounding(
                context,
                "installed",
                upstream_id="installed-package-2",
                extract_text="Independent installed behavior confirms research-tree ships version 2 in the public release.",
            ),
        ),
    )

    assert assessment.state is ClaimState.CORROBORATED
    assert assessment.decision_authority is True


def test_same_content_with_different_upstream_labels_remains_isolated(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assessment = ClaimAdmissionEvaluator(context.resolver).assess(
        _claim(),
        (
            _grounding(context, "primary", upstream_id="official-release-2", content_fingerprint="release-2-bytes"),
            _grounding(context, "mirror", upstream_id="mirror-release-2", content_fingerprint="release-2-bytes"),
        ),
    )

    assert assessment.state is ClaimState.ISOLATED
    assert assessment.provenance_clusters == ("official-release-2",)


def test_non_entailing_or_stale_grounding_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assessment = ClaimAdmissionEvaluator(context.resolver).assess(
        _claim(),
        (
            _grounding(
                context,
                "wrong-version",
                upstream_id="release-note-1",
                extract_text="research-tree ships version 1 in the public release",
                version="1",
            ),
        ),
    )

    assert assessment.state is ClaimState.REJECTED
    assert assessment.decision_authority is False
    assert assessment.rejection_reasons == ("extract-does-not-entail-claim",)


def test_material_isolated_claim_prevents_search_stop(tmp_path: Path) -> None:
    context = _context(tmp_path)
    claim_assessment = ClaimAdmissionEvaluator(context.resolver).assess(
        _claim(), (_grounding(context, "one", upstream_id="release-note-2"),)
    )

    result = assess_acquisition_batch(
        assessment_id="assessment-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        outcomes=(_outcome(),),
        claim_assessments=(claim_assessment,),
    )

    assert result.disposition == "deepen"
    assert result.next_actions == ("cross-validate-material-claims",)
