from pathlib import Path

from test_search_portfolio import execution_outcome, portfolio, registration

from research_tree import (
    ContentAddressedStore,
    DurableSourceCaptureService,
    MethodRegistration,
    MethodRegistry,
    PortfolioBatch,
    RunLedger,
    SearchPortfolioExecutor,
)


def test_acquisition_receipt_is_bound_after_cas_capture(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-1")
    service = DurableSourceCaptureService(ledger, ContentAddressedStore(tmp_path))
    capture = service.capture(
        run_id="run-1",
        capture_id="capture-a",
        attempt_id="attempt-a",
        data=b"bytes",
        media_type="text/plain",
        method_id="web",
        provider_id="provider",
        expected_revision=0,
    )
    receipt = service.receipt(
        run_id="run-1",
        receipt_id="receipt-a",
        capture=capture,
        attempt_id="attempt-a",
        method_id="web",
        provider_id="provider",
        expected_revision=1,
    )
    assert receipt.capture_id == capture.capture_id
    assert receipt.artifact_ref is not None


def test_executor_accepts_adapter_outcomes_without_persisting_coordinator_state() -> None:
    value = portfolio(
        selected_methods=(
            portfolio().selected_methods[0],
            type(portfolio().selected_methods[0])(
                method_id="repository-inspection",
                provider_id="provider-b",
                failure_boundary="provider-b-boundary",
                query_refs=("query-2",),
                selection_reason="independence",
            ),
        ),
        rejected_methods=(),
    )
    methods = MethodRegistry(
        registry_id="registry-1",
        registrations=(
            registration("web-search", "provider-a"),
            MethodRegistration(
                method_id="repository-inspection",
                provider_id="provider-b",
                capability="repository-inspection",
                failure_boundary="provider-b-boundary",
                availability="available",
            ),
        ),
    )

    result = SearchPortfolioExecutor(methods).execute(
        value,
        (
            PortfolioBatch(
                "batch-1",
                "portfolio-1",
                (
                    execution_outcome(),
                    execution_outcome(
                        outcome_id="outcome-2",
                        method_id="repository-inspection",
                        provider_id="provider-b",
                    ),
                ),
            ),
        ),
    )

    assert len(result.assessments) == 1
    assert result.assessments[0].provenance_independence == "independent"
    assert result.assessments[0].disposition == "stop"


def test_executor_run_invokes_only_registered_method_boundaries() -> None:
    value = portfolio(rejected_methods=())
    methods = MethodRegistry(
        registry_id="registry-1",
        registrations=(registration("web-search", "provider-a"),),
    )
    seen: list[tuple[str, str]] = []

    def adapter(selection):
        seen.append(selection.boundary)
        return execution_outcome()

    result = SearchPortfolioExecutor(methods).run(
        value,
        {("web-search", "provider-a"): adapter},
    )

    assert seen == [("web-search", "provider-a")]
    assert result.assessments[0].disposition == "deepen"
    assert result.assessments[0].next_actions == ("cross-validate-material-claims",)
