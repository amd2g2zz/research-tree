from __future__ import annotations

from research_tree.claims import Claim, ClaimAdmissionEvaluator, ClaimGrounding, ClaimState, ProvenanceDescriptor
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


def _grounding(
    grounding_id: str,
    *,
    upstream_id: str,
    extract_text: str = "research-tree ships version 2 in the public release",
    source_revision: str = "2026-08-01",
    version: str = "2",
    content_fingerprint: str | None = None,
) -> ClaimGrounding:
    return ClaimGrounding(
        grounding_id=grounding_id,
        claim_id="claim-release-version",
        capture_ref=f"capture-{grounding_id}",
        extract_ref=f"extract-{grounding_id}",
        original_wording=extract_text,
        source_revision=source_revision,
        source_version=version,
        source_time_range="2026-08",
        source_scope="public release",
        source_conditions=("default distribution",),
        provenance=ProvenanceDescriptor(
            upstream_id=upstream_id,
            owner_id="research-tree",
            content_fingerprint=content_fingerprint or upstream_id,
        ),
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


def test_same_upstream_through_two_providers_remains_isolated() -> None:
    assessment = ClaimAdmissionEvaluator().assess(
        _claim(),
        (
            _grounding("one", upstream_id="release-note-2"),
            _grounding("two", upstream_id="release-note-2"),
        ),
    )

    assert assessment.state is ClaimState.ISOLATED
    assert assessment.provenance_clusters == ("release-note-2",)
    assert assessment.decision_authority is False


def test_independent_entailing_sources_corroborate_claim() -> None:
    assessment = ClaimAdmissionEvaluator().assess(
        _claim(),
        (
            _grounding("official", upstream_id="release-note-2"),
            _grounding("installed", upstream_id="installed-package-2"),
        ),
    )

    assert assessment.state is ClaimState.CORROBORATED
    assert assessment.decision_authority is True


def test_same_content_with_different_upstream_labels_remains_isolated() -> None:
    assessment = ClaimAdmissionEvaluator().assess(
        _claim(),
        (
            _grounding("primary", upstream_id="official-release-2", content_fingerprint="release-2-bytes"),
            _grounding("mirror", upstream_id="mirror-release-2", content_fingerprint="release-2-bytes"),
        ),
    )

    assert assessment.state is ClaimState.ISOLATED
    assert assessment.provenance_clusters == ("official-release-2",)


def test_non_entailing_or_stale_grounding_is_rejected() -> None:
    assessment = ClaimAdmissionEvaluator().assess(
        _claim(),
        (
            _grounding(
                "wrong-version",
                upstream_id="release-note-1",
                extract_text="research-tree ships version 1 in the public release",
                source_revision="2025-08-01",
                version="1",
            ),
        ),
    )

    assert assessment.state is ClaimState.REJECTED
    assert assessment.decision_authority is False
    assert assessment.rejection_reasons == ("extract-does-not-entail-claim",)


def test_material_isolated_claim_prevents_search_stop() -> None:
    claim_assessment = ClaimAdmissionEvaluator().assess(_claim(), (_grounding("one", upstream_id="release-note-2"),))

    result = assess_acquisition_batch(
        assessment_id="assessment-1",
        portfolio_id="portfolio-1",
        batch_id="batch-1",
        outcomes=(_outcome(),),
        claim_assessments=(claim_assessment,),
    )

    assert result.disposition == "deepen"
    assert result.next_actions == ("cross-validate-material-claims",)
