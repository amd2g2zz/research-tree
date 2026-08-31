"""Surviving public-case and time-split-case contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def api():
    from research_tree import InvalidEvaluationError, TimeSplitCase

    return {
        "InvalidEvaluationError": InvalidEvaluationError,
        "TimeSplitCase": TimeSplitCase,
    }


def case_mapping() -> dict[str, object]:
    return {
        "id": "case-worker-isolation",
        "corpus_version": "2026.1",
        "source": {
            "locator": "https://github.com/example/worker-service",
            "permission": "public repository fixture",
        },
        "baseline": {
            "revision": "2f4a1b7",
            "sha256": "a" * 64,
        },
        "environment": {
            "image": "python:3.12-slim",
            "digest": "sha256:" + "b" * 64,
            "recipe": "uv sync --locked; uv run python -m pytest -q",
        },
        "public_materials": (
            {
                "kind": "issue",
                "locator": "https://github.com/example/worker-service/issues/42",
            },
        ),
        "hidden_oracle_id": "oracle-worker-isolation-v2",
        "limitations": ("The fixture omits deployment-only behavior.",),
    }


def test_versioned_public_case_set_has_pinned_baselines_without_hidden_material() -> None:
    api_modules = api()
    path = Path(__file__).parents[1] / "evaluation" / "cases" / "v1.json"
    case_set = json.loads(path.read_text(encoding="utf-8"))

    assert case_set["schema_version"] == "1"
    assert case_set["corpus_version"] == "2026.1"
    cases = tuple(api_modules["TimeSplitCase"].from_mapping(case) for case in case_set["cases"])
    assert {case.id for case in cases} == {
        "click-isolated-filesystem",
        "requests-contributing-link",
    }
    for case in cases:
        assert len(case.baseline["revision"]) == 40
        assert len(case.baseline["sha256"]) == 64
        assert case.environment["digest"].startswith("sha256:")
        assert "pull" not in case.to_dict()["public_materials"][0]["locator"]


def test_case_rejects_eventual_patch_discussion_and_hidden_test_material() -> None:
    api_modules = api()
    invalid = case_mapping()
    invalid["eventual_patch"] = "diff --git a/secret"

    with pytest.raises(api_modules["InvalidEvaluationError"], match="hidden"):
        api_modules["TimeSplitCase"].from_mapping(invalid)
