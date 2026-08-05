"""Black-box fixtures and conservative attribution helpers for alpha2."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


CONTROLLED_FACTORS = ("model", "host", "skill_revision", "brief", "context_pack", "tools", "authority", "oracle", "environment")


def assess_attribution(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify observations without turning one transcript into causality.

    A controlled comparison needs two runs with identical non-declared factors
    and a different declared factor.  Missing or unavailable runs remain
    unresolved and can never satisfy a release gate.
    """

    normalized = [dict(run) for run in runs]
    if len(normalized) < 2:
        return {
            "classification": "observation" if normalized else "missing",
            "causal_attribution": "unresolved",
            "release_eligible": False,
            "reason": "a single transcript cannot identify a model or host cause",
        }
    unavailable = [run for run in normalized if run.get("availability") == "unavailable"]
    if unavailable:
        return {
            "classification": "comparison_unavailable",
            "causal_attribution": "unresolved",
            "release_eligible": False,
            "reason": "one or more registered runtimes are unavailable",
        }
    declared = {str(run.get("declared_factor", "")) for run in normalized}
    changed = {factor for factor in CONTROLLED_FACTORS if len({run.get(factor) for run in normalized}) > 1}
    if len(normalized) != 2 or len(declared) != 1 or not declared or changed != declared:
        return {
            "classification": "non_controlled_comparison",
            "causal_attribution": "unresolved",
            "release_eligible": False,
            "changed_factors": sorted(changed),
            "reason": "brief, context, tools, authority, oracle, environment and skill must be held constant",
        }
    outcomes = [run.get("result") for run in normalized]
    differs = outcomes[0] != outcomes[1]
    return {
        "classification": "controlled_comparison",
        "causal_attribution": "supported" if differs else "not_supported",
        "release_eligible": differs,
        "declared_factor": next(iter(declared)),
        "changed_factors": sorted(changed),
    }


def reported_claude_glm_fixture() -> dict[str, Any]:
    """Return the redacted public portion of the reported failure fixture."""

    return {
        "id": "claude-glm52-research-tree-v1",
        "corpus_version": "alpha2",
        "kind": "black_box_regression",
        "public_turns": [
            {"kind": "initial_brief", "text": "A vague technical research request."},
            {"kind": "correction", "text": "The previously inferred subject is not the target."},
            {"kind": "depth_request", "text": "The report must be professional and evidence anchored."},
        ],
        "checks": [
            "activation_before_reference",
            "one_open_prompt",
            "correction_invalidation",
            "task_identity_isolation",
            "recursive_continuation",
            "controlled_attribution",
            "dual_delivery_depth",
        ],
        "hidden_oracle_id": "oracle-claude-glm52-v1",
        "limitations": ["The fixture does not itself prove a GLM5.2 causal effect."],
    }
