"""Parent acceptance checks for the #83 SearchPortfolio children."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"
COMPARISON = (
    ROOT
    / "openspec"
    / "changes"
    / "accept-intent-derived-search-portfolios"
    / "evidence"
    / "search-portfolio-historical-baseline-v1.json"
)
DEPTH_RANK = {"snippet": 1, "full-source": 3}


def _registry(name: str) -> dict[str, object]:
    return json.loads((REGISTRIES / name).read_text(encoding="utf-8"))


def _group(payload: dict[str, object], group_id: int) -> dict[str, object]:
    groups = payload["groups"]
    assert isinstance(groups, list)
    return next(item for item in groups if item["group"] == group_id)


def _capability(rows: list[object], name: str) -> dict[str, object]:
    return next(item for item in rows if item["capability"] == name)


def _fixture_digest(reference_input: dict[str, object]) -> str:
    serialized = json.dumps(reference_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _side_metrics(side: dict[str, object], denominator: int) -> dict[str, float | int]:
    observation_ids = side["observation_ids"]
    covered_subquestion_ids = side["covered_subquestion_ids"]
    assert isinstance(observation_ids, list)
    assert isinstance(covered_subquestion_ids, list)
    assert all(isinstance(identifier, str) for identifier in observation_ids)
    assert all(isinstance(identifier, str) for identifier in covered_subquestion_ids)
    depth = side["depth"]
    closure = side["decision_closure"]
    assert isinstance(depth, str)
    assert closure in {"open", "closed"}
    return {
        "rediscovery": len(observation_ids) - len(set(observation_ids)),
        "coverage": len(set(covered_subquestion_ids)) / denominator,
        "depth": DEPTH_RANK[depth],
        "decision_closure": int(closure == "closed"),
    }


def test_parent_group_binds_reachable_search_portfolio_children_and_current_surfaces() -> None:
    execution = _registry("task-execution-v1.json")
    verification = _registry("task-verification-v1.json")
    issue_map = _registry("issue-execution-map-v1.json")
    matrix = _registry("delivery-matrix-v1.json")

    parent = _group(execution, 27)
    assert parent["depends_on"] == [74, 75, 77]
    assert parent["outputs"] == ["search-portfolio-parent-acceptance"]
    assert "retain bounded legacy" not in parent["rollback"]
    assert "do not restore a legacy query path" in parent["rollback"]
    assert _group(verification, 27)["state"] in {"planned", "verified"}

    for child in (74, 75, 77):
        receipt = _group(verification, child)["command_receipt"]
        assert isinstance(receipt, dict)
        revision = receipt["source_revision"]
        assert isinstance(revision, str)
        assert (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
                cwd=ROOT,
                check=False,
            ).returncode
            == 0
        )

    planner_receipt = _group(verification, 74)["command_receipt"]
    assert isinstance(planner_receipt, dict)
    assert planner_receipt["source_revision"] == "34d1c2b28592ad28b1277f973a51e2b0c0899f7f"
    assert planner_receipt["command"] == _group(execution, 74)["acceptance_command"]

    issues = issue_map["issues"]
    assert isinstance(issues, list)
    issue = next(item for item in issues if item["issue"] == 83)
    assert issue["primary_group"] == 27
    assert issue["supporting_groups"] == [15, 74, 75, 77]
    assert issue["openspec_change"] == "accept-intent-derived-search-portfolios"

    rows = matrix["capability_rows"]
    assert isinstance(rows, list)
    acquisition = _capability(rows, "research-acquisition")
    assert acquisition["source_modules"] == [
        "src/research_tree/search_portfolio.py",
        "src/research_tree/source_capture.py",
        "src/research_tree/coordinator.py",
    ]
    assert acquisition["public_surface"] == [
        "SearchPortfolioExecutor",
        "DurableSourceCaptureService",
        "ResearchRunCoordinator.persist_search_portfolio_lineage",
    ]

    portfolio = _capability(rows, "search-portfolios")
    assert portfolio["source_modules"] == [
        "src/research_tree/search_portfolio.py",
        "src/research_tree/coordinator.py",
    ]
    assert portfolio["public_surface"] == [
        "SearchPortfolio",
        "MethodRegistry",
        "IntentDerivedSearchPortfolioPlanner",
        "SearchPortfolioExecutor",
        "ResearchRunCoordinator.persist_search_portfolio_lineage",
    ]

    acceptance = _capability(rows, "search-portfolio-aggregate-acceptance")
    assert acceptance["task_groups"] == [27]
    assert acceptance["github_issue"] == "#83"


def test_static_historical_baseline_recomputes_only_explicit_deltas() -> None:
    payload = json.loads(COMPARISON.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["comparison_kind"] == "static_historical_baseline"
    assert payload["issue_ref"] == "#83"
    assert payload["release_manifest_link"] == "evaluation/results/alpha2-release-candidate-v1.json"
    assert payload["release_decision_claim"] == "none"

    reference_input = payload["reference_input"]
    assert isinstance(reference_input, dict)
    subquestion_ids = reference_input["subquestion_ids"]
    assert isinstance(subquestion_ids, list)
    assert len(subquestion_ids) == len(set(subquestion_ids))
    assert payload["reference_input_digest"] == _fixture_digest(reference_input)

    retired = payload["retired_direct_query"]
    portfolio = payload["portfolio"]
    assert isinstance(retired, dict)
    assert isinstance(portfolio, dict)
    retired_metrics = _side_metrics(retired, len(subquestion_ids))
    portfolio_metrics = _side_metrics(portfolio, len(subquestion_ids))
    assert retired["metrics"] == retired_metrics
    assert portfolio["metrics"] == portfolio_metrics

    deltas = payload["deltas"]
    assert deltas == {
        key: portfolio_metrics[key] - retired_metrics[key]
        for key in ("rediscovery", "coverage", "depth", "decision_closure")
    }
    assert payload["child_groups"] == [74, 75, 77]
    assert payload["limitations"]
    assert payload["trace_refs"]

    serialized = json.dumps(payload, sort_keys=True).lower()
    for forbidden in ("raw_query", "private_prompt", "import ", "research-tree run"):
        assert forbidden not in serialized
