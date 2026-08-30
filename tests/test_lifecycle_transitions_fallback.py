"""Issue #381: _load_lifecycle_transitions must surface missing/malformed matrix.

ADR-002 mandates the lifecycle transition matrix as the single authoritative
source. The legacy ``pass; return _TRANSITIONS`` silent fallback hides
governance drift. These tests pin the new strict-loading contract:

* missing matrix file -> CoordinatorError (no legacy fallback)
* malformed JSON       -> CoordinatorError
* missing ``transitions`` key -> CoordinatorError
* empty ``transitions`` list  -> CoordinatorError
* valid matrix         -> loaded dict (no behavior change for happy path)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


class _MatrixPathFactory:
    """Stub for ``Path`` that redirects ``Path(__file__).resolve().parents[2]``
    to ``tmp_path`` so each test can supply its own matrix fixture.

    The chain works because ``parents[2]`` returns a real ``pathlib.Path``
    (``tmp_path``), and the subsequent ``/ "openspec" / ...`` segments build
    a real path object on top of that real path.
    """

    def __init__(self, redirect_to: Path) -> None:
        self._redirect_to = redirect_to

    def __call__(self, *args: object, **kwargs: object) -> "_MatrixPathFactory":
        # ``Path(__file__)`` invocation -> return self so the chain continues.
        return self

    def resolve(self) -> "_MatrixPathFactory":
        return self

    @property
    def parents(self) -> list[Path]:
        # parents[2] is the project root in the original layout
        return [self, self, self._redirect_to]  # type: ignore[list-item]

    def __truediv__(self, other: object) -> Path:
        if isinstance(other, str):
            return self._redirect_to / other
        return self  # type: ignore[return-value]


def _patch_matrix_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace ``Path`` inside the coordinator module with the test factory."""
    factory = _MatrixPathFactory(tmp_path)
    monkeypatch.setattr("research_tree.coordinator.Path", factory)


def _matrix_dir(tmp_path: Path) -> Path:
    return tmp_path / "openspec" / "changes" / "unify-research-runtime-alpha2" / "registries"


def _valid_matrix_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "transitions": [
            {"from": "alignment", "event": "go", "to": "alignment", "actor": "coordinator"},
            {"from": "alignment", "event": "exit", "to": "handoff_pending", "actor": "human"},
        ],
    }


def test_missing_matrix_raises_coordinator_config_error(tmp_path, monkeypatch, caplog) -> None:
    """Missing matrix file must raise; legacy fallback is a regression."""
    from research_tree import coordinator
    from research_tree.coordinator import CoordinatorError

    _patch_matrix_path(monkeypatch, tmp_path)
    # Deliberately do not create any matrix file under tmp_path.

    with caplog.at_level(logging.ERROR):
        with pytest.raises(CoordinatorError, match="canonical_lifecycle_matrix"):
            coordinator._load_lifecycle_transitions()

    assert "canonical_lifecycle_matrix" in caplog.text


def test_malformed_json_raises(tmp_path, monkeypatch, caplog) -> None:
    """Malformed JSON must raise; legacy fallback is a regression."""
    from research_tree import coordinator
    from research_tree.coordinator import CoordinatorError

    matrix_dir = _matrix_dir(tmp_path)
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "lifecycle-matrix-v1.json").write_text("not valid json", encoding="utf-8")
    _patch_matrix_path(monkeypatch, tmp_path)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(CoordinatorError, match="canonical_lifecycle_matrix"):
            coordinator._load_lifecycle_transitions()

    assert "canonical_lifecycle_matrix" in caplog.text


def test_missing_transitions_key_raises(tmp_path, monkeypatch, caplog) -> None:
    """Matrix without ``transitions`` key must raise."""
    from research_tree import coordinator
    from research_tree.coordinator import CoordinatorError

    matrix_dir = _matrix_dir(tmp_path)
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "lifecycle-matrix-v1.json").write_text("{}", encoding="utf-8")
    _patch_matrix_path(monkeypatch, tmp_path)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(CoordinatorError, match="canonical_lifecycle_matrix"):
            coordinator._load_lifecycle_transitions()

    assert "canonical_lifecycle_matrix_malformed" in caplog.text


def test_empty_transitions_raises(tmp_path, monkeypatch, caplog) -> None:
    """Empty ``transitions`` list must raise (no edges = no contract)."""
    from research_tree import coordinator
    from research_tree.coordinator import CoordinatorError

    matrix_dir = _matrix_dir(tmp_path)
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "lifecycle-matrix-v1.json").write_text(json.dumps({"transitions": []}), encoding="utf-8")
    _patch_matrix_path(monkeypatch, tmp_path)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(CoordinatorError, match="canonical_lifecycle_matrix"):
            coordinator._load_lifecycle_transitions()

    assert "canonical_lifecycle_matrix_malformed" in caplog.text


def test_valid_matrix_returns_dict(tmp_path, monkeypatch) -> None:
    """Happy path: a well-formed matrix must load and return the edges dict."""
    from research_tree import coordinator

    matrix_dir = _matrix_dir(tmp_path)
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "lifecycle-matrix-v1.json").write_text(json.dumps(_valid_matrix_payload()), encoding="utf-8")
    _patch_matrix_path(monkeypatch, tmp_path)

    result = coordinator._load_lifecycle_transitions()

    expected = {
        ("alignment", "go"): ("alignment", "coordinator"),
        ("alignment", "exit"): ("handoff_pending", "human"),
    }
    assert result == expected
