from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from context_ledger_contract import ContextBudget, ContextLedgerError, ContextReadLedger  # noqa: E402


def ledger(workspace: Path, budget: ContextBudget | None = None) -> ContextReadLedger:
    run_root = workspace / ".research-tree" / "projects" / "project-a" / "runs" / "run-a"
    run_root.mkdir(parents=True)
    return ContextReadLedger(workspace, run_root, "run-a", budget=budget)


def test_records_digest_range_consumer_phase_and_visible_cache(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    context_ledger = ledger(tmp_path)

    fresh = context_ledger.record_read(
        source,
        consumer="researcher-a",
        phase="landscape",
        byte_start=0,
        byte_end=5,
        input_tokens=120,
        tool_output_tokens=4,
        process_output_tokens=7,
    )
    cached = context_ledger.record_read(
        source,
        consumer="researcher-a",
        phase="validation",
        byte_start=0,
        byte_end=5,
        input_tokens=80,
    )
    replayed = context_ledger.record_read(
        source,
        consumer="reviewer-b",
        phase="adversarial",
        byte_start=0,
        byte_end=5,
        input_tokens=60,
    )

    assert fresh["records"][0]["disposition"] == "fresh"
    assert fresh["records"][0]["line_start"] == 1
    assert fresh["records"][0]["line_end"] == 1
    assert cached["records"][1]["disposition"] == "cached"
    assert replayed["records"][2]["disposition"] == "replayed"
    assert replayed["read_counts"] == {"fresh": 1, "cached": 1, "replayed": 1}
    assert replayed["token_totals"] == {
        "fresh_input_tokens": 120,
        "cached_input_tokens": 80,
        "replayed_input_tokens": 60,
        "tool_output_tokens": 4,
        "process_output_tokens": 7,
    }
    assert replayed["duplicate_read_ratio"] == pytest.approx(2 / 3)
    assert replayed["evidence_coverage"] == {"unique_source_digests": 1, "unique_digest_ranges": 1}


def test_active_output_stays_excluded_until_sealed_and_digest_bound(tmp_path: Path) -> None:
    active_output = tmp_path / ".research-tree" / "runtime.log"
    active_output.parent.mkdir()
    active_output.write_text("sealed evidence", encoding="utf-8")
    ordinary_source = tmp_path / "source.md"
    ordinary_source.write_text("ordinary", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("ignored", encoding="utf-8")
    context_ledger = ledger(tmp_path)

    with pytest.raises(ContextLedgerError, match="active_output_unsealed"):
        context_ledger.record_read(active_output, consumer="reader", phase="validation")
    assert ordinary_source.resolve() in context_ledger.discover_sources()
    assert active_output.resolve() not in context_ledger.discover_sources()

    context_ledger.seal_source(active_output)
    assert active_output.resolve() in context_ledger.discover_sources()
    context_ledger.record_read(active_output, consumer="reader", phase="validation")
    active_output.write_text("changed after sealing", encoding="utf-8")
    with pytest.raises(ContextLedgerError, match="sealed_source_changed"):
        context_ledger.record_read(active_output, consumer="reader", phase="validation")


def test_budget_exhaustion_is_resumable_unknown_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("bounded", encoding="utf-8")
    context_ledger = ledger(tmp_path, ContextBudget(max_fresh_input_tokens=10))

    exhausted = context_ledger.record_read(source, consumer="reader", phase="landscape", input_tokens=11)

    assert exhausted["status"] == "budget_exceeded"
    assert exhausted["execution_state"] == "unknown"
    assert exhausted["completion_authority"] == "none"
    assert exhausted["checkpoint"] == {
        "reason": "budget_exceeded",
        "reasons": ["fresh_input_tokens_exceeded"],
        "resumable": True,
        "wave": 1,
    }
    with pytest.raises(ContextLedgerError, match="resume"):
        context_ledger.record_read(source, consumer="reader", phase="validation")

    resumed = context_ledger.resume(ContextBudget(max_cached_input_tokens=100))

    assert resumed["status"] == "active"
    assert resumed["execution_state"] == "unknown"
    assert resumed["wave"] == 2
    assert resumed["checkpoint"] is None
