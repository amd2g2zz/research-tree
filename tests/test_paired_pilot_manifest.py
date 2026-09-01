"""Issue #335: the paired-pilot manifest must satisfy its identity contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "evaluation/pilot/paired-pilot-v1.json").read_text(encoding="utf-8"))


@pytest.fixture
def validate() -> "importlib.util.ModuleType":
    path = ROOT / "evaluation/pilot/validate.py"
    spec = importlib.util.spec_from_file_location("paired_pilot_validate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_manifest_is_valid(validate) -> None:
    validate.validate_manifest(MANIFEST)


def test_missing_required_field_fails(validate) -> None:
    broken = {key: value for key, value in MANIFEST.items() if key != "rubric_version"}
    with pytest.raises(validate.PilotManifestError, match="rubric_version"):
        validate.validate_manifest(broken)


def test_arm_model_revision_mismatch_fails(validate) -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["model"]["same_revision_both_arms"] = False
    with pytest.raises(validate.PilotManifestError, match="same model revision"):
        validate.validate_manifest(broken)


def test_case_count_outside_bounds_fails(validate) -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["cases"] = broken["cases"][:6]
    with pytest.raises(validate.PilotManifestError, match="8-12"):
        validate.validate_manifest(broken)


def test_domain_below_two_fails(validate) -> None:
    broken = json.loads(json.dumps(MANIFEST))
    del broken["cases"][1]
    with pytest.raises(validate.PilotManifestError, match="sparse"):
        validate.validate_manifest(broken)


def test_holdout_overlap_fails(validate) -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["cases"][0]["non_holdout"] = False
    with pytest.raises(validate.PilotManifestError, match="non_holdout"):
        validate.validate_manifest(broken)
