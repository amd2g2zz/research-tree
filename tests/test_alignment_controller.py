from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]


def controller():
    path = ROOT / "scripts" / "alignment_controller.py"
    spec = importlib.util.spec_from_file_location("alignment_controller_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")


def complete_graph() -> dict[str, object]:
    required = {
        "goal": ("outcome", "Produce an implementation-driving technical strategy."),
        "use": ("intended_use", "Use the result to authorize and plan implementation."),
        "scope": ("scope_boundary", "Research and design only; no implementation yet."),
        "delivery": ("delivery", "Deliver a professional evidence-anchored technical package."),
        "authority": ("authority", "The agent owns autonomous research after confirmation."),
        "success": ("success_oracle", "Every P0 decision has evidence and a validation oracle."),
        "feasibility": ("feasibility", "The strategy is technically plausible in the stated environment."),
        "strategy": ("strategy", "Use recursive decision-risk research with independent validation."),
    }
    nodes: list[dict[str, object]] = [
        {
            "id": node_id,
            "type": node_type,
            "statement": statement,
            "status": "supported",
            "impact": 5,
            "human_only": False,
            "confidence": "high",
            "source": "joint",
        }
        for node_id, (node_type, statement) in required.items()
    ]
    nodes.extend(
        [
            {
                "id": "question-architecture",
                "type": "research_question",
                "statement": "Which architecture best satisfies the confirmed strategy?",
                "status": "candidate",
                "impact": 5,
                "human_only": False,
                "confidence": "low",
                "source": "joint",
                "oracle": "The leading architecture survives an independent executable validation.",
            },
            {
                "id": "evidence-recon",
                "type": "evidence",
                "statement": "Initial reconnaissance found a persisted coordinator pattern.",
                "status": "supported",
                "impact": 3,
                "human_only": False,
                "confidence": "medium",
                "source": "reconnaissance",
                "attributes": {
                    "anchor": {"kind": "source", "ref": "https://example.test/coordinator"}
                },
            },
        ]
    )
    return {
        "nodes": nodes,
        "edges": [
            {
                "id": "edge-recon-supports",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "supports",
                "status": "active",
                "confidence": "medium",
                "provenance": "alignment reconnaissance turn 1",
            },
            {
                "id": "edge-recon-limits",
                "source_id": "evidence-recon",
                "target_id": "question-architecture",
                "relation": "limits",
                "status": "active",
                "confidence": "low",
                "provenance": "alignment reconnaissance turn 2",
            },
        ],
    }


def test_controller_asks_one_high_impact_gap_then_switches_to_reconnaissance(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "alignment-run")
    gaps = tmp_path / "gaps.json"
    write_json(
        gaps,
        {
            "gaps": [
                {
                    "id": f"gap-{index}",
                    "summary": f"intent dimension {index}",
                    "impact": index,
                    "human_only": True,
                }
                for index in range(1, 6)
            ]
        },
    )

    decision = module.plan(tmp_path, "alignment-run", gaps)
    assert decision["action"] == "ask_one"
    assert decision["gap_id"] == "gap-5"
    assert " and " not in decision["question"].lower()

    module.record(tmp_path, "alignment-run", "gap-5", "unchanged", "same-state")
    module.record(tmp_path, "alignment-run", "gap-5", "unchanged", "same-state")
    third = module.record(
        tmp_path,
        "alignment-run",
        "gap-5",
        "unchanged",
        "same-state",
    )
    assert third["stagnant_turns"] == 2
    assert module.plan(tmp_path, "alignment-run", gaps)["action"] == "reconnaissance"


def test_controller_requires_explicit_handoff_confirmation(tmp_path: Path) -> None:
    module = controller()
    module.init(tmp_path, "handoff-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())

    decision = module.plan(tmp_path, "handoff-run", graph)
    assert decision["action"] == "await_human_confirmation"
    with pytest.raises(module.ControllerError, match="confirmation"):
        module.confirm(tmp_path, "handoff-run", "okay")
    with pytest.raises(module.ControllerError, match="digest"):
        module.confirm(
            tmp_path,
            "handoff-run",
            "I confirm the strategy and authorize autonomous research.",
        )

    result = module.confirm(
        tmp_path,
        "handoff-run",
        "I confirm the stated outcome and authorize autonomous research within that scope.",
        decision["alignment_digest"],
    )
    assert result["status"] == "autonomous"
    assert result["phase"] == "research"

    compiled = module.AlignmentGraphStore(
        module.database_path(tmp_path, "handoff-run")
    ).compile_handoff()
    assert compiled["alignment_digest"] == decision["alignment_digest"]
    assert compiled["compiled_graph_digest"] != compiled["alignment_digest"]
    assert set(compiled["decision_slots"]) == {"question-architecture"}
    assert len(compiled["baseline_findings"]) == 1
    assert compiled["execution_context"]["authority"] == [
        "The agent owns autonomous research after confirmation."
    ]
    paths = compiled["baseline_findings"][0]["observations"][0]["alignment_paths"]
    assert {path[0]["relation"] for path in paths} == {"supports", "limits"}
    output = tmp_path / "compiled-handoff.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "alignment_controller.py"),
            "--workspace",
            str(tmp_path),
            "compile",
            "--run-id",
            "handoff-run",
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert json.loads(output.read_text(encoding="utf-8"))["kind"] == "alignment-handoff"


def test_handoff_preserves_indirect_evidence_paths(tmp_path: Path) -> None:
    module = controller()
    module.init(tmp_path, "indirect-run")
    update = complete_graph()
    update["nodes"].append(
        {
            "id": "argument-architecture",
            "type": "argument",
            "statement": "The coordinator pattern constrains the architecture.",
            "status": "supported",
            "source": "agent",
        }
    )
    update["edges"] = [
        {
            "id": "edge-evidence-argument",
            "source_id": "evidence-recon",
            "target_id": "argument-architecture",
            "relation": "supports",
        },
        {
            "id": "edge-argument-question",
            "source_id": "argument-architecture",
            "target_id": "question-architecture",
            "relation": "limits",
        },
    ]
    graph = tmp_path / "indirect.json"
    write_json(graph, update)
    decision = module.plan(tmp_path, "indirect-run", graph)
    assert decision["action"] == "await_human_confirmation"
    module.confirm(
        tmp_path,
        "indirect-run",
        "I confirm the strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    compiled = module.AlignmentGraphStore(
        module.database_path(tmp_path, "indirect-run")
    ).compile_handoff()
    path = compiled["baseline_findings"][0]["observations"][0]["alignment_paths"][0]
    assert [edge["relation"] for edge in path] == ["supports", "limits"]


def test_refined_research_question_replaces_old_obligation_and_reanchors_evidence(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "refinement-run")
    update = complete_graph()
    update["nodes"].append(
        {
            "id": "question-old",
            "type": "research_question",
            "statement": "Which broad architecture might work?",
            "status": "candidate",
            "impact": 4,
            "human_only": False,
            "confidence": "low",
            "source": "agent",
            "oracle": "A broad architecture is bounded.",
        }
    )
    update["edges"] = [
        {
            "id": "edge-evidence-old",
            "source_id": "evidence-recon",
            "target_id": "question-old",
            "relation": "supports",
        },
        {
            "id": "edge-new-refines-old",
            "source_id": "question-architecture",
            "target_id": "question-old",
            "relation": "refines",
        },
    ]
    graph = tmp_path / "refinement.json"
    write_json(graph, update)
    decision = module.plan(tmp_path, "refinement-run", graph)
    assert decision["action"] == "await_human_confirmation"
    module.confirm(
        tmp_path,
        "refinement-run",
        "I confirm the refined strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    compiled = module.AlignmentGraphStore(
        module.database_path(tmp_path, "refinement-run")
    ).compile_handoff()
    assert set(compiled["decision_slots"]) == {"question-architecture"}
    path = compiled["baseline_findings"][0]["observations"][0]["alignment_paths"][0]
    assert [edge["direction"] for edge in path] == ["forward", "reverse"]


def test_schema_command_writes_strict_utf8_and_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    module = controller()
    output = tmp_path / "alignment-schema.json"
    assert module.main(["--workspace", str(tmp_path), "schema", "--output", str(output)]) == 0
    assert not output.read_bytes().startswith(b"\xef\xbb\xbf")
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["encoding"] == "UTF-8 without BOM"
    module.init(tmp_path, "strict-schema-run")
    bad = tmp_path / "bad-update.json"
    write_json(
        bad,
        {"nodes": [{"id": "bad", "type": "unknown", "statement": "x", "owner": "human"}]},
    )
    with pytest.raises(module.ControllerError, match="unknown fields"):
        module.plan(tmp_path, "strict-schema-run", bad)


def test_alignment_database_preserves_parallel_edges_and_rebuilds_view(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "multigraph-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    module.plan(tmp_path, "multigraph-run", graph)
    database = module.database_path(tmp_path, "multigraph-run")
    store = module.AlignmentGraphStore(database)
    state = store.status()

    assert len(state["graph"]["edges"]) == 2
    assert {
        (edge["source_id"], edge["target_id"])
        for edge in state["graph"]["edges"]
    } == {("evidence-recon", "question-architecture")}
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 3
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM edges")
        connection.execute("DELETE FROM nodes")

    rebuilt = store.rebuild_materialized()
    assert len(rebuilt["graph"]["nodes"]) == len(complete_graph()["nodes"])
    assert len(rebuilt["graph"]["edges"]) == 2


def test_confirm_rejects_stale_displayed_graph(tmp_path: Path) -> None:
    module = controller()
    module.init(tmp_path, "stale-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, "stale-run", graph)
    update = complete_graph()
    update["nodes"][0]["statement"] = "A materially revised implementation outcome."
    changed = tmp_path / "changed.json"
    write_json(changed, update)
    module.plan(tmp_path, "stale-run", changed)

    with pytest.raises(module.ControllerError, match="changed"):
        module.confirm(
            tmp_path,
            "stale-run",
            "I accept this strategy and authorize autonomous research.",
            decision["alignment_digest"],
        )


def test_readiness_rejects_supported_evidence_that_handoff_would_drop(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "evidence-quality-run")
    update = complete_graph()
    update["nodes"][-1]["attributes"] = {}
    graph = tmp_path / "missing-anchor.json"
    write_json(graph, update)

    decision = module.plan(tmp_path, "evidence-quality-run", graph)
    assert decision["action"] == "reconnaissance"
    assert any(
        "no structured anchor" in reason for reason in decision["readiness"]["reasons"]
    )


def test_handoff_excludes_explicitly_superseded_research_obligation(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "supersession-run")
    update = complete_graph()
    update["nodes"].append(
        {
            "id": "unknown-architecture",
            "type": "unknown",
            "statement": "Which broad architecture might work?",
            "status": "candidate",
            "impact": 4,
            "human_only": False,
            "confidence": "low",
            "source": "agent",
            "oracle": "A broad architecture is named.",
        }
    )
    update["edges"].append(
        {
            "id": "edge-question-supersedes-unknown",
            "source_id": "question-architecture",
            "target_id": "unknown-architecture",
            "relation": "supersedes",
            "status": "active",
            "confidence": "high",
            "provenance": "alignment refinement",
        }
    )
    graph = tmp_path / "supersession.json"
    write_json(graph, update)
    decision = module.plan(tmp_path, "supersession-run", graph)
    assert decision["action"] == "await_human_confirmation"
    module.confirm(
        tmp_path,
        "supersession-run",
        "I accept the refined strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )

    compiled = module.AlignmentGraphStore(
        module.database_path(tmp_path, "supersession-run")
    ).compile_handoff()
    assert set(compiled["decision_slots"]) == {"question-architecture"}
    assert compiled["diagnostics"]["excluded_superseded_nodes"] == [
        {
            "node_id": "unknown-architecture",
            "superseded_by": ["question-architecture"],
        }
    ]


def test_confirmed_graph_initializes_persisted_tree_with_zero_delta_baseline(
    tmp_path: Path,
) -> None:
    from research_tree import (
        ResearchTreeStateError,
        RunLedger,
        initialize_research_from_alignment,
    )

    module = controller()
    module.init(tmp_path, "integration-run")
    graph = tmp_path / "graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, "integration-run", graph)
    module.confirm(
        tmp_path,
        "integration-run",
        "I accept the displayed strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )

    ledger = RunLedger(tmp_path / "run-ledger")
    ledger.create_run("round-alignment")
    tree = initialize_research_from_alignment(
        ledger,
        round_id="round-alignment",
        tree_id="research-tree",
        alignment_database=module.database_path(tmp_path, "integration-run"),
        expected_revision=ledger.get_revision("round-alignment"),
    )

    assert tree.payload["transition_index"] == 0
    assert tree.payload["delta_history"] == ()
    assert len(tree.payload["consumed_finding_ids"]) == 1
    assert tree.payload["execution_context"]["scope_boundaries"] == (
        "Research and design only; no implementation yet.",
    )
    root = tree.payload["nodes"]["root:question-architecture"]
    assert root["status"] == "frontier"
    assert root["decision_oracle"] == (
        "The leading architecture survives an independent executable validation."
    )
    parent_ids = {ref.artifact_id for ref in tree.parent_refs}
    assert set(tree.payload["consumed_finding_ids"]) < parent_ids
    assert len(parent_ids) == 2
    assert any(artifact_id.startswith("alignment-handoff-") for artifact_id in parent_ids)

    artifact_count = len(ledger.load_run("round-alignment").artifacts)
    with pytest.raises(ResearchTreeStateError, match="already exists"):
        initialize_research_from_alignment(
            ledger,
            round_id="round-alignment",
            tree_id="research-tree",
            alignment_database=module.database_path(tmp_path, "integration-run"),
            expected_revision=ledger.get_revision("round-alignment"),
        )
    assert len(ledger.load_run("round-alignment").artifacts) == artifact_count


def test_alignment_handoff_batch_rolls_back_every_artifact_on_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_tree import RunLedger, initialize_research_from_alignment

    module = controller()
    module.init(tmp_path, "atomic-run")
    graph = tmp_path / "atomic-graph.json"
    write_json(graph, complete_graph())
    decision = module.plan(tmp_path, "atomic-run", graph)
    module.confirm(
        tmp_path,
        "atomic-run",
        "I accept the displayed strategy and authorize autonomous research.",
        decision["alignment_digest"],
    )
    ledger = RunLedger(tmp_path / "run-ledger")
    ledger.create_run("round-alignment")

    def fail_commit() -> None:
        raise RuntimeError("injected alignment handoff failure")

    monkeypatch.setattr(RunLedger, "_before_commit", staticmethod(fail_commit))
    with pytest.raises(RuntimeError, match="injected alignment handoff failure"):
        initialize_research_from_alignment(
            ledger,
            round_id="round-alignment",
            tree_id="research-tree",
            alignment_database=module.database_path(tmp_path, "atomic-run"),
            expected_revision=ledger.get_revision("round-alignment"),
        )

    assert ledger.get_revision("round-alignment") == 0
    assert ledger.load_run("round-alignment").artifacts == ()


def test_controller_rejects_utf8_bom_instead_of_silently_using_utf8_sig(
    tmp_path: Path,
) -> None:
    module = controller()
    module.init(tmp_path, "encoding-run")
    gaps = tmp_path / "bom-gaps.json"
    gaps.write_bytes(b"\xef\xbb\xbf" + b'{"gaps": []}')

    with pytest.raises(module.ControllerError, match="cannot read graph update"):
        module.plan(tmp_path, "encoding-run", gaps)
