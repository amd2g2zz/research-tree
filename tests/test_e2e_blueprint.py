from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from test_openspec_export import complete_package


@dataclass
class HighRiskAdapter:
    request: object | None = None

    def run(self, request):
        from research_tree import IsolatedVerificationResult

        self.request = request
        names = ("build", "hidden_acceptance", "regression")
        return IsolatedVerificationResult(
            check_kind=request.check_kind,
            status="pass",
            commands=tuple({"name": name, "command": f"fake-{name}"} for name in names),
            results=tuple(
                {
                    "name": name,
                    "status": "pass",
                    "summary": f"The isolated {name} check passed.",
                }
                for name in names
            ),
            isolation={
                "host_secrets_exposed": False,
                "repository_mutated": False,
                "isolated_working_copy": True,
                "network_access": "disabled",
            },
        )


@dataclass
class IndependentRunner:
    request: object | None = None

    def run(self, request):
        from research_tree import EvaluationCheck, IndependentEvaluationResult

        self.request = request
        return IndependentEvaluationResult(
            checks=(
                EvaluationCheck("build", "pass", "fake-build", "The build passed."),
                EvaluationCheck(
                    "fail_to_pass",
                    "pass",
                    "fake-hidden-acceptance",
                    "The hidden acceptance check passed.",
                ),
                EvaluationCheck(
                    "pass_to_pass",
                    "pass",
                    "fake-regression",
                    "The regression check passed.",
                ),
            ),
            limitations=("The smoke test uses deterministic evaluator adapters.",),
        )


def case():
    from research_tree import TimeSplitCase

    return TimeSplitCase.from_mapping(
        {
            "id": "e2e-worker-boundary",
            "corpus_version": "e2e-v1",
            "source": {
                "locator": "https://example.test/e2e-worker-boundary",
                "permission": "local deterministic fixture",
            },
            "baseline": {"revision": "fixture-v1", "sha256": "a" * 64},
            "environment": {
                "image": "python:3.12-slim",
                "digest": "sha256:" + "b" * 64,
                "recipe": "uv run python -m pytest -q",
            },
            "public_materials": ({"kind": "repository_baseline", "locator": "fixture:repository"},),
            "hidden_oracle_id": "e2e-hidden-oracle-v1",
            "limitations": ("This fixture is a controlled integration smoke test.",),
        }
    )


def baseline():
    from research_tree import EvaluationCheck, SimplerBaselineResult

    return SimplerBaselineResult(
        name="direct-brief",
        checks=(
            EvaluationCheck("build", "pass", "fake-build", "The baseline built."),
            EvaluationCheck(
                "fail_to_pass",
                "fail",
                "fake-hidden-acceptance",
                "The baseline misses the requested worker boundary.",
            ),
            EvaluationCheck(
                "pass_to_pass",
                "pass",
                "fake-regression",
                "The baseline preserves existing behavior.",
            ),
        ),
        limitations=("The direct brief has no decision ledger or readiness evidence.",),
    )


def test_blueprint_spine_reaches_safe_handoff_then_explicit_export(tmp_path: Path) -> None:
    from research_tree import (
        ASSURANCE_ADAPTER_SELECTION_KIND,
        BlueprintEvaluationSuite,
        OpenSpecExporter,
        ReadinessVerifier,
        readiness_for_delivery,
    )

    modules, store, round_record, technical_package = complete_package(tmp_path)
    snapshot = store.load_round(round_record.id)
    human_brief = next(item for item in snapshot.artifacts if item.kind == "human-research-report")
    assert technical_package.kind == "technical-research-package"
    assert human_brief.payload["technical_package_ref"] == {
        "round_id": round_record.id,
        "artifact_id": technical_package.id,
        "revision": technical_package.revision,
    }
    assert not [item for item in snapshot.artifacts if item.kind == ASSURANCE_ADAPTER_SELECTION_KIND]

    high_risk_adapter = HighRiskAdapter()
    readiness = ReadinessVerifier(store).verify(
        round_id=round_record.id,
        readiness_id="readiness-e2e",
        technical_package=technical_package,
        repository_roots={"input-repository": tmp_path / "repository"},
        risk_tier="high",
        verification_adapter=high_risk_adapter,
    )
    assert high_risk_adapter.request is not None
    assert not hasattr(high_risk_adapter.request, "repository_roots")
    assert readiness_for_delivery(readiness)["gates"]["implementation_readiness"] == "pass"
    assert readiness.payload["risk_verification"]["executed_checks"][0]["check"] == ("independent_implementation_run")

    independent_runner = IndependentRunner()
    evaluation = BlueprintEvaluationSuite(store).evaluate(
        round_id=round_record.id,
        evaluation_id="evaluation-e2e",
        case=case(),
        technical_package=technical_package,
        readiness_record=readiness,
        cost={"tool_calls": 9, "seconds": 45},
        clarification_burden={"asked": 0, "unanswered": 0},
        implementation_runner=independent_runner,
        baseline_result=baseline(),
    )
    assert independent_runner.request is not None
    assert not hasattr(independent_runner.request, "hidden_oracle_id")
    assert evaluation.payload["structural_quality"]["traceability"] == "pass"
    assert evaluation.payload["implementation_outcome"]["checks"][1]["name"] == "fail_to_pass"

    openspec_root = tmp_path / "openspec"
    assert not openspec_root.exists()
    exported = OpenSpecExporter(store).export(
        round_id=round_record.id,
        technical_package=technical_package,
        openspec_root=openspec_root,
        change_name="e2e-worker-boundary",
    )
    assert exported.change_directory.exists()
    assert (exported.change_directory / "tasks.md").exists()
