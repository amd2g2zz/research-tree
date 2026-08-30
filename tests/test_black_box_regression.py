"""Issue #323: black-box regression evaluation for cognition, growth, disagreement."""

from __future__ import annotations

import json

from research_tree.black_box_regression import (
    BlackBoxFixture,
    FixtureSuite,
    discover_fixtures,
    parse_fixture,
    score_run,
)


def test_discover_fixtures_returns_suites() -> None:
    fixtures = discover_fixtures("alpha3-batch2")
    assert isinstance(fixtures, list)
    assert len(fixtures) > 0


def test_fixture_suite_carries_metadata() -> None:
    suite = FixtureSuite(
        id="alpha3-batch2",
        domain="cognition",
        cases=(
            BlackBoxFixture(
                id="fx-1",
                domain="cognition",
                prompt="test prompt",
                expected_outcome="completed",
                evidence_requirements=("claim_admitted",),
            ),
        ),
    )
    assert suite.id == "alpha3-batch2"
    assert suite.cases[0].id == "fx-1"
    assert suite.cases[0].domain == "cognition"


def test_black_box_fixture_requires_evidence_not_belief() -> None:
    """A test that admits evidence-free human beliefs to supported is a regression."""

    fixture = BlackBoxFixture(
        id="fx-1",
        domain="cognition",
        prompt="test",
        expected_outcome="completed",
        evidence_requirements=("claim_admitted",),
    )
    bad = {"belief_status": "supported", "basis_refs": ()}
    assert score_run(fixture, bad) is False, "evidence-free belief must NOT pass"


def test_parse_fixture_loads_valid_record(tmp_path) -> None:
    record = {
        "id": "fx-parse",
        "domain": "cognition",
        "prompt": "x",
        "expected_outcome": "completed",
        "evidence_requirements": ["claim_admitted"],
    }
    path = tmp_path / "fx.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    fixture = parse_fixture(path)
    assert fixture.id == "fx-parse"
    assert fixture.evidence_requirements == ("claim_admitted",)


def test_score_run_requires_both_problem_topology_and_pressure_resistance() -> None:
    fixture = BlackBoxFixture(
        id="fx-1",
        domain="cognition",
        prompt="x",
        expected_outcome="completed",
        evidence_requirements=("claim_admitted", "pressure_resisted"),
    )
    # Only problem topology admitted, no pressure resistance
    partial = {"problem_topology_admitted": True, "pressure_resisted": False}
    assert score_run(fixture, partial) is False
    # Both
    full = {"problem_topology_admitted": True, "pressure_resisted": True, "claim_admitted": True}
    assert score_run(fixture, full) is True


def test_discover_fixtures_filters_by_suite_id() -> None:
    fixtures = discover_fixtures("nonexistent-suite")
    assert fixtures == []
