"""Issue #333: scheduling converges to a single authority (coordinator + policy).

The retired orchestration module must vanish from the public API, and the
adaptive policy must be consulted on the dispatch decision path.
"""

from __future__ import annotations

import pytest
from test_research_run_coordinator import _confirm_strategy, _initialize

from research_tree.coordinator import LEASE_KIND, ResearchRunCoordinator
from research_tree.policy import AdaptiveResearchPolicy


def test_orchestration_plan_is_removed_from_public_api() -> None:
    import research_tree

    assert not hasattr(research_tree, "compile_orchestration_plan")
    with pytest.raises(ImportError):
        from research_tree import compile_orchestration_plan  # noqa: F401


def test_dispatch_without_policy_keeps_current_behavior(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    lease = coordinator.dispatch(
        run_id="run-57",
        work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
        worker_id="worker-1",
        expected_revision=ledger.get_revision("run-57"),
        attempt_id="attempt-1",
    )
    assert lease.kind == LEASE_KIND
    assert lease.payload["policy_proposal_id"] is None


def test_dispatch_consults_wired_policy_and_records_proposal_lineage(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    _confirm_strategy(ledger, coordinator)
    wired = ResearchRunCoordinator(ledger, policy=AdaptiveResearchPolicy(seed=7))
    calls: list[dict] = []
    original = AdaptiveResearchPolicy.evaluate

    def _spy(self, *args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return original(self, *args, **kwargs)

    AdaptiveResearchPolicy.evaluate = _spy
    try:
        lease = wired.dispatch(
            run_id="run-57",
            work_item={"work_item_id": "work-1", "objective": "inspect", "success_oracle": "oracle-1"},
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-57"),
            attempt_id="attempt-2",
        )
    finally:
        AdaptiveResearchPolicy.evaluate = original
    assert calls, "wired policy must be consulted on the dispatch decision path"
    assert lease.payload["policy_proposal_id"] is not None


def test_coordinator_accepts_policy_without_changing_rejections(tmp_path) -> None:
    ledger, coordinator, _, _, _ = _initialize(tmp_path)
    wired = ResearchRunCoordinator(ledger, policy=AdaptiveResearchPolicy())
    with pytest.raises(Exception, match="unverifiable_work_item"):
        wired.dispatch(
            run_id="run-57",
            work_item={"work_item_id": "work-x", "objective": "no oracle"},
            worker_id="worker-1",
            expected_revision=ledger.get_revision("run-57"),
        )
