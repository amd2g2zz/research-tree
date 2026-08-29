"""Issue #335: the paired-pilot manifest must satisfy its identity contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "evaluation/pilot/paired-pilot-v1.json").read_text(encoding="utf-8"))


def _validate_module():
    path = ROOT / "evaluation/pilot/validate.py"
    spec = importlib.util.spec_from_file_location("paired_pilot_validate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_validate = _validate_module()
PilotManifestError = _validate.PilotManifestError
validate_manifest = _validate.validate_manifest


def test_repository_manifest_is_valid() -> None:
    validate_manifest(MANIFEST)


def test_missing_required_field_fails() -> None:
    broken = {key: value for key, value in MANIFEST.items() if key != "rubric_version"}
    with pytest.raises(PilotManifestError, match="rubric_version"):
        validate_manifest(broken)


def test_arm_model_revision_mismatch_fails() -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["model"]["same_revision_both_arms"] = False
    with pytest.raises(PilotManifestError, match="same model revision"):
        validate_manifest(broken)


def test_case_count_outside_bounds_fails() -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["cases"] = broken["cases"][:6]
    with pytest.raises(PilotManifestError, match="8-12"):
        validate_manifest(broken)


def test_domain_below_two_fails() -> None:
    broken = json.loads(json.dumps(MANIFEST))
    del broken["cases"][1]
    with pytest.raises(PilotManifestError, match="sparse"):
        validate_manifest(broken)


def test_holdout_overlap_fails() -> None:
    broken = json.loads(json.dumps(MANIFEST))
    broken["cases"][0]["non_holdout"] = False
    with pytest.raises(PilotManifestError, match="non_holdout"):
        validate_manifest(broken)
