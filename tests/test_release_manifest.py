import json
import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_public_release_case_and_retained_manifest_are_governed() -> None:
    cases = json.loads((ROOT / "evaluation/cases/alpha2-release-v1.json").read_text(encoding="utf-8"))
    retained = json.loads((ROOT / "evaluation/results/alpha2-release-candidate-v1.json").read_text(encoding="utf-8"))

    assert cases["schema_version"] == 1
    assert {item["category"] for item in cases["cases"]} >= {
        "false-completion",
        "repository-research",
        "recovery",
        "contradiction",
        "multimodal",
        "recursive-discovery",
        "unavailable-tool",
        "provider-failure",
        "post-handoff-feedback",
    }
    assert all("hidden_oracle_id" in item and "hidden_oracle" not in item for item in cases["cases"])
    assert retained["case_id"] == cases["id"]
    assert retained["release_decision"]["status"] in {"pass", "fail"}
    assert retained["limitations"]


def test_release_harness_is_a_deterministic_public_entrypoint() -> None:
    path = ROOT / "evaluation/harness/run_release_gates.py"
    spec = importlib.util.spec_from_file_location("run_release_gates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    first = module.run(ROOT / "evaluation/results/alpha2-release-candidate-v1.json")
    second = module.run(ROOT / "evaluation/results/alpha2-release-candidate-v1.json")

    assert first == second
    assert first["manifest_id"] == "alpha2-release-candidate-v1"
