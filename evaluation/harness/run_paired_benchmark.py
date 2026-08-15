"""Run or honestly report the evaluator-owned paired research benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).parents[2]
DISPOSABLE_ROOT = ROOT / ".research-tree" / "evaluation-runs"


def _benchmark_module():
    path = Path(__file__).with_name("paired_benchmark.py")
    spec = importlib.util.spec_from_file_location("paired_benchmark", path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load paired benchmark harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _is_evaluator_owned(path: Path) -> bool:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return True
    try:
        resolved.relative_to(DISPOSABLE_ROOT)
    except ValueError:
        return False
    return True


def _require_evaluator_owned(path: Path, label: str) -> None:
    if not _is_evaluator_owned(path):
        raise ValueError(f"{label} must remain outside the tracked repository or under disposable evaluation runs")


def _load_attestation_key(path: Path) -> bytes:
    _require_evaluator_owned(path, "review attestation key")
    key = path.read_bytes().strip()
    if not key:
        raise ValueError("review attestation key must not be empty")
    return key


def run(
    manifest_path: Path | None,
    records_path: Path | None,
    review_attestation_key_path: Path | None = None,
) -> dict[str, object]:
    harness = _benchmark_module()
    if manifest_path is None and records_path is None and review_attestation_key_path is None:
        return harness.benchmark_unavailable(
            "sealed manifest and records are evaluator-owned and have not been supplied"
        )
    if manifest_path is None or records_path is None or review_attestation_key_path is None:
        raise ValueError("sealed manifest, records, and review attestation key must be supplied together")
    _require_evaluator_owned(manifest_path, "sealed manifest")
    _require_evaluator_owned(records_path, "benchmark records")
    return harness.analyze_benchmark(
        _load_mapping(manifest_path, "sealed manifest"),
        _load_mapping(records_path, "records"),
        review_attestation_key=_load_attestation_key(review_attestation_key_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--records", type=Path)
    parser.add_argument("--review-attestation-key-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect-status", choices=("analyzed", "failed-integrity", "unavailable"))
    args = parser.parse_args(argv)
    try:
        result = run(args.manifest, args.records, args.review_attestation_key_file)
        if args.output:
            _require_evaluator_owned(args.output, "output")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.expect_status:
        return 0 if result["status"] == args.expect_status else 1
    return 0 if result["status"] == "analyzed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
