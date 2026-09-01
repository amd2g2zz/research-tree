from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_tree.skill_activation import (
    build_loader_receipt,
    evaluate_activation_gate,
    loader_integrity_status,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = {
    "codex": ROOT / "packages" / "codex" / "research-tree",
    "claude": ROOT / "packages" / "claude-code" / "research-tree" / "skills" / "research-tree",
    "hermes": ROOT / "packages" / "hermes" / "research-tree",
}


@pytest.mark.parametrize("host", ["codex", "claude", "hermes"])
@pytest.mark.parametrize("mutation", ["first", "middle", "tail", "truncate"])
def test_skill_mutation_invalidates_receipt_for_every_host(host: str, mutation: str, tmp_path: Path) -> None:
    package = tmp_path / host
    shutil.copytree(PACKAGE_DIRS[host], package)
    receipt = build_loader_receipt(package, host=host, session_id="fault-session")
    skill = package / "SKILL.md"
    payload = bytearray(skill.read_bytes())
    if mutation == "first":
        payload[0] ^= 1
    elif mutation == "middle":
        payload[len(payload) // 2] ^= 1
    elif mutation == "tail":
        payload[-1] ^= 1
    else:
        payload = payload[: max(1, len(payload) // 2)]
    skill.write_bytes(bytes(payload))
    result = loader_integrity_status(package, host=host, receipt=receipt, session_id="fault-session")
    assert result["state"] == "invalid_loader_receipt"


@pytest.mark.parametrize("host", ["codex", "claude", "hermes"])
def test_wrong_session_or_host_receipt_never_becomes_valid(host: str, tmp_path: Path) -> None:
    package = tmp_path / host
    shutil.copytree(PACKAGE_DIRS[host], package)
    receipt = build_loader_receipt(package, host=host, session_id="session-a")
    assert loader_integrity_status(package, host=host, receipt=receipt, session_id="session-b")["state"] == (
        "invalid_loader_receipt"
    )
    other = "claude" if host != "claude" else "codex"
    assert loader_integrity_status(package, host=other, receipt=receipt, session_id="session-a")["state"] == (
        "invalid_loader_receipt"
    )


@pytest.mark.parametrize(
    "loader,alignment,handoff,action",
    [
        ("unverified_loader_integrity", "equilibrium", "confirmed", "research"),
        ("live_verified", "pending", "confirmed", "research"),
        ("live_verified", "equilibrium", "implicit", "dispatch"),
        ("live_verified", "equilibrium", "confirmed", "unknown"),
    ],
)
def test_activation_boundary_injection_is_blocked(loader: str, alignment: str, handoff: str, action: str) -> None:
    result = evaluate_activation_gate(
        loader_state=loader,
        alignment_state=alignment,
        handoff_state=handoff,
        requested_action=action,
    )
    assert result["state"] == "blocked"
