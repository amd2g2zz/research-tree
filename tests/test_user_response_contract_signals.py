"""Issue #490: the persisted user-response class feeds contract-term selection.

The five prompt-signal classes (correction/interruption/insight/answer/
neutral) stop being metadata-only: a small policy table maps the observed
signal plus the outstanding ask onto contract-term adjustments (cost_cap,
taboos, target_gap directive) and a typed user move in the turn_contract
seam's response classes. The hook feeds the typed verdict to the run surface
during the alignment phase, fail-open. Scenario names follow the spec delta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_tree.alignment_turn_record import AlignmentTurnRecordStore
from research_tree.decision_frame import (
    GAP_DIRECTIVES,
    USER_SIGNAL_CATEGORIES,
    resolve_user_response_policy,
)
from research_tree.lifecycle_hook import (
    ALIGNMENT_USER_MOVE_ROUTE,
    PROMPT_SIGNAL_CATEGORIES,
    observe,
)
from research_tree.turn_contract import (
    RESPONSE_CLASSES,
    RESPONSE_CLASS_DISCRIMINATION,
    RESPONSE_CLASS_GENERATION,
    CostCap,
    ContractTerms,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT_PARTS = (".research-tree", "projects", "topic-1", "runs", "run-1")
VERDICT_KEYS = {
    "user_move",
    "category",
    "confidence",
    "rule",
    "cost_cap",
    "taboo_additions",
    "taboo_removals",
    "gap_directive",
    "gap_target",
    "reason",
}
ASKED_NODE = "gap.auth-model"
SETTLED_NODE = "gap.settled-axis"
NEXT_NODE = "gap.data-retention"


def ask_terms(**overrides: object) -> ContractTerms:
    values: dict[str, object] = {
        "target_gap": ASKED_NODE,
        "required_traces": (),
        "cost_cap": CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None),
        "taboos": (SETTLED_NODE,),
    }
    values.update(overrides)
    return ContractTerms(**values)


def signal(category: str, confidence: str = "high", rule: str = "rule") -> dict[str, str]:
    return {"category": category, "confidence": confidence, "rule": rule}


def project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "packages").mkdir()
    (tmp_path / "skill-src").mkdir()
    return tmp_path


def project_run(root: Path, *, phase: str | None = None) -> Path:
    run_root = root.joinpath(*RUN_ROOT_PARTS)
    manifest = run_root / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, str] = {"project_id": "topic-1", "run_id": "run-1"}
    if phase is not None:
        document["phase"] = phase
    manifest.write_text(json.dumps(document) + "\n", encoding="utf-8")
    return run_root


def seeded_store(run_root: Path, terms: ContractTerms | None = None) -> AlignmentTurnRecordStore:
    store = AlignmentTurnRecordStore(run_root)
    store.append(
        turn_index=1,
        mirror="the brief is understood",
        gap="which auth model the product uses",
        delta_summary="asked about the auth model",
        user_move=RESPONSE_CLASS_GENERATION,
        contract_terms=terms,
    )
    return store


def submit(root: Path, prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "cwd": str(root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "project_id": "topic-1",
        "run_id": "run-1",
    }
    return observe(payload, host="claude", event="UserPromptSubmit", project_root=root, process_cwd=root)


def fed_user_move_records(run_root: Path) -> list[dict[str, object]]:
    directory = run_root / "events"
    if not directory.is_dir():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("route") == ALIGNMENT_USER_MOVE_ROUTE:
            records.append(record)
    return records


@pytest.fixture(autouse=True)
def clean_phase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCH_TREE_RUN_PHASE", raising=False)


class TestPolicyTable:
    def test_correction_after_an_ask_lowers_the_next_cost_cap_and_reopens_the_node(self) -> None:
        verdict = resolve_user_response_policy(
            signal("correction", "high", "explicit_wrong"), ask_terms(), candidates=(ASKED_NODE, NEXT_NODE)
        )
        assert verdict.user_move == RESPONSE_CLASS_GENERATION
        # The ceiling drops from unbounded generation to a bounded budget.
        assert verdict.cost_cap == CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=2)
        # The corrected node is re-opened: taboo removal plus a reopen directive.
        assert verdict.taboo_additions == ()
        assert verdict.taboo_removals == (ASKED_NODE,)
        assert verdict.gap_directive == "reopen"
        assert verdict.gap_target == ASKED_NODE
        assert verdict.to_dict().keys() == VERDICT_KEYS

    def test_repeated_correction_drops_the_ceiling_to_the_one_sentence_floor(self) -> None:
        verdict = resolve_user_response_policy(
            signal("correction", "high", "explicit_no"), ask_terms(), previous_category="correction"
        )
        assert verdict.cost_cap == CostCap(response_class=RESPONSE_CLASS_DISCRIMINATION, max_sentences=1)
        assert verdict.taboo_removals == (ASKED_NODE,)
        assert verdict.gap_directive == "reopen"

    def test_answer_marks_the_asked_node_answered_and_advances_target_gap_selection_away_from_it(self) -> None:
        verdict = resolve_user_response_policy(
            signal("answer", "low", "direct_affirmative"),
            ask_terms(),
            candidates=(ASKED_NODE, NEXT_NODE, SETTLED_NODE),
        )
        assert verdict.user_move == RESPONSE_CLASS_DISCRIMINATION
        assert verdict.taboo_additions == (ASKED_NODE,)
        assert verdict.taboo_removals == ()
        assert verdict.gap_directive == "advance"
        # Selection advances past the answered node and skips the settled taboo.
        assert verdict.gap_target == NEXT_NODE
        assert verdict.cost_cap is None

    def test_interruption_redirects_target_gap_ranking_toward_the_new_material(self) -> None:
        verdict = resolve_user_response_policy(
            signal("interruption", "high", "explicit_stop"), ask_terms(), candidates=(ASKED_NODE, NEXT_NODE)
        )
        assert verdict.user_move == RESPONSE_CLASS_GENERATION
        assert verdict.gap_directive == "redirect"
        # The interrupted node is demoted, not tabooed: it stays open.
        assert verdict.taboo_additions == ()
        assert verdict.taboo_removals == ()
        assert verdict.gap_target == NEXT_NODE
        # New material raises the response-production ceiling.
        assert verdict.cost_cap == CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None)

    def test_interruption_without_candidates_still_names_the_redirect(self) -> None:
        verdict = resolve_user_response_policy(signal("interruption", "high", "explicit_stop"), ask_terms())
        assert verdict.gap_directive == "redirect"
        assert verdict.gap_target is None

    def test_insight_raises_the_ceiling_without_redirecting(self) -> None:
        verdict = resolve_user_response_policy(
            signal("insight", "low", "volunteered_observation"), ask_terms(), candidates=(ASKED_NODE, NEXT_NODE)
        )
        assert verdict.cost_cap == CostCap(response_class=RESPONSE_CLASS_GENERATION, max_sentences=None)
        assert verdict.gap_directive == "keep"
        assert verdict.gap_target is None
        assert verdict.taboo_additions == ()

    def test_neutral_turns_leave_contract_terms_unchanged(self) -> None:
        verdict = resolve_user_response_policy(signal("neutral", "low", "default"), ask_terms(), candidates=(NEXT_NODE,))
        assert verdict.cost_cap is None
        assert verdict.taboo_additions == ()
        assert verdict.taboo_removals == ()
        assert verdict.gap_directive == "keep"
        assert verdict.gap_target is None
        assert verdict.user_move == RESPONSE_CLASS_GENERATION

    def test_correction_with_continuation_semantics_leaves_terms_unchanged(self) -> None:
        verdict = resolve_user_response_policy(
            signal("correction", "low", "explicit_wrong+continuation"), ask_terms(), candidates=(NEXT_NODE,)
        )
        assert verdict.cost_cap is None
        assert verdict.taboo_additions == ()
        assert verdict.taboo_removals == ()
        assert verdict.gap_directive == "keep"
        assert verdict.gap_target is None

    def test_a_correction_never_raises_an_emitted_cost_cap(self) -> None:
        floor = CostCap(response_class=RESPONSE_CLASS_DISCRIMINATION, max_sentences=1)
        verdict = resolve_user_response_policy(signal("correction", "medium", "actually_prefix"), ask_terms(cost_cap=floor))
        assert verdict.cost_cap == floor

    def test_answer_without_an_outstanding_ask_keeps_terms_unchanged(self) -> None:
        verdict = resolve_user_response_policy(signal("answer", "low", "direct_affirmative"), None)
        assert verdict.user_move == RESPONSE_CLASS_DISCRIMINATION
        assert verdict.cost_cap is None
        assert verdict.taboo_additions == ()
        assert verdict.taboo_removals == ()
        assert verdict.gap_directive == "keep"
        assert verdict.gap_target is None

    def test_signal_categories_match_the_hook_vocabulary(self) -> None:
        assert USER_SIGNAL_CATEGORIES == set(PROMPT_SIGNAL_CATEGORIES)
        assert GAP_DIRECTIVES == {"advance", "reopen", "redirect", "keep"}
        assert RESPONSE_CLASSES == ("discrimination", "generation")

    def test_unknown_signal_category_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="category is unsupported"):
            resolve_user_response_policy(signal("gossip"), None)
        with pytest.raises(ValueError, match="previous signal category is unsupported"):
            resolve_user_response_policy(signal("neutral"), None, previous_category="gossip")

    def test_candidates_must_be_node_ids(self) -> None:
        with pytest.raises(ValueError, match="node id"):
            resolve_user_response_policy(signal("answer"), ask_terms(), candidates=("not a node id!",))


class TestHookPlumbing:
    def test_alignment_phase_prompt_feeds_the_typed_user_move_and_policy_verdict(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="alignment")
        seeded_store(run_root, terms=ask_terms())
        result = submit(root, "No, use pytest not unittest")
        assert result["status"] == "recorded"
        verdict = result["user_move_policy"]
        assert isinstance(verdict, dict)
        assert verdict.keys() == VERDICT_KEYS
        assert verdict["user_move"] == RESPONSE_CLASS_GENERATION
        assert verdict["cost_cap"] == {"response_class": RESPONSE_CLASS_GENERATION, "max_sentences": 2}
        assert verdict["gap_directive"] == "reopen"
        assert verdict["taboo_removals"] == [ASKED_NODE]
        feeds = fed_user_move_records(run_root)
        assert len(feeds) == 1
        feed = feeds[0]
        assert feed["route"] == ALIGNMENT_USER_MOVE_ROUTE
        assert feed["category"] == "correction"
        assert feed["user_move_policy"]["user_move"] in RESPONSE_CLASSES
        signals_dir = root / ".research-tree-debug" / "signals"
        signal_record = json.loads(next(signals_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert signal_record["user_move_policy"]["gap_directive"] == "reopen"

    def test_repeated_corrections_across_prompts_drop_to_the_floor(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="alignment")
        seeded_store(run_root, terms=ask_terms())
        first = submit(root, "No, use pytest not unittest")
        assert isinstance(first["user_move_policy"], dict)
        assert first["user_move_policy"]["cost_cap"] == {
            "response_class": RESPONSE_CLASS_GENERATION,
            "max_sentences": 2,
        }
        second = submit(root, "wrong, the API paginates")
        assert isinstance(second["user_move_policy"], dict)
        assert second["user_move_policy"]["cost_cap"] == {
            "response_class": RESPONSE_CLASS_DISCRIMINATION,
            "max_sentences": 1,
        }

    def test_an_answer_advances_away_from_the_asked_node_end_to_end(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="alignment")
        seeded_store(run_root, terms=ask_terms())
        result = submit(root, "yes, option a")
        verdict = result["user_move_policy"]
        assert isinstance(verdict, dict)
        assert verdict["user_move"] == RESPONSE_CLASS_DISCRIMINATION
        assert verdict["taboo_additions"] == [ASKED_NODE]
        assert verdict["gap_directive"] == "advance"
        assert verdict["gap_target"] is None  # no candidates at hook level; #489 resolves

    def test_outside_the_alignment_phase_nothing_is_fed(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="research")
        result = submit(root, "status")
        assert "user_move_policy" not in result
        assert fed_user_move_records(run_root) == []
        # The #503 re-entry protocol is untouched.
        assert result["reentry"]["path"] == "status_echo"

    def test_unphased_runs_produce_no_verdict(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root)
        result = submit(root, "please continue with the implementation")
        assert "user_move_policy" not in result
        assert fed_user_move_records(run_root) == []

    def test_without_an_active_run_no_verdict_is_produced(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        result = submit(root, "please continue with the implementation")
        assert result["status"] == "recorded"
        assert "user_move_policy" not in result

    def test_a_missing_turn_record_degrades_to_a_terms_less_verdict(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="alignment")
        result = submit(root, "No, use pytest not unittest")
        verdict = result["user_move_policy"]
        assert isinstance(verdict, dict)
        # Without an outstanding ask the cap row still applies but nothing is re-opened.
        assert verdict["gap_directive"] == "keep"
        assert verdict["taboo_removals"] == []
        assert verdict["cost_cap"] == {"response_class": RESPONSE_CLASS_GENERATION, "max_sentences": 2}

    def test_a_corrupt_turn_record_degrades_fail_open(self, tmp_path: Path) -> None:
        root = project(tmp_path)
        run_root = project_run(root, phase="alignment")
        records = run_root / "alignment" / "turn-records.jsonl"
        records.parent.mkdir(parents=True, exist_ok=True)
        records.write_text("{not json}\n", encoding="utf-8")
        result = submit(root, "No, use pytest not unittest")
        assert result["status"] == "recorded"
        assert "user_move_policy" not in result


class TestComparisonDocument:
    def test_the_comparison_document_exists_and_names_the_decision(self) -> None:
        document = (ROOT / "openspec" / "changes" / "user-response-contract-signals" / "design.md").read_text(
            encoding="utf-8"
        )
        assert "## Strategy-selection design comparison" in document
        # All three options are compared.
        assert "### Option (a) — small policy table over contract terms (CHOSEN)" in document
        assert "### Option (b) — bandit for cost-cap tuning (DEFERRED, rejected for beta1)" in document
        assert "### Option (c) — full MDP over interaction history (REJECTED)" in document
        # The decision names the policy table and records the rejected alternatives.
        assert "### Decision" in document
        assert "Implement **(a) the small policy table** now" in document
