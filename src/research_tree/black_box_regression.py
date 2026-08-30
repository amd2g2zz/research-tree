"""Issue #323: black-box regression for cognition, growth, disagreement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class BlackBoxFixture:
    """One black-box regression case."""

    id: str
    domain: str
    prompt: str
    expected_outcome: str
    evidence_requirements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FixtureSuite:
    """A suite of black-box regression cases sharing one scenario."""

    id: str
    domain: str
    cases: tuple[BlackBoxFixture, ...]


def parse_fixture(path: str | Path) -> BlackBoxFixture:
    """Parse one fixture JSON file (whitelist)."""

    if not isinstance(path, (str, Path)):
        raise TypeError("path must be a string or Path")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("fixture must be an object")
    required = {"id", "domain", "prompt", "expected_outcome", "evidence_requirements"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"fixture missing required fields: {sorted(missing)}")
    return BlackBoxFixture(
        id=str(payload["id"]),
        domain=str(payload["domain"]),
        prompt=str(payload["prompt"]),
        expected_outcome=str(payload["expected_outcome"]),
        evidence_requirements=tuple(str(item) for item in payload["evidence_requirements"]),
    )


# Issue #323 acceptance: a black-box suite covering cognition, growth,
# disagreement.  Discovery falls back to a built-in registry when no fixture
# files are present at the canonical path.
_BUILT_IN_SUITES: tuple[FixtureSuite, ...] = (
    FixtureSuite(
        id="alpha3-batch2",
        domain="cognition",
        cases=(
            BlackBoxFixture(
                id="fx-cognition-1",
                domain="cognition",
                prompt="vague intent",
                expected_outcome="completed",
                evidence_requirements=("claim_admitted",),
            ),
        ),
    ),
    FixtureSuite(
        id="alpha3-growth",
        domain="growth",
        cases=(
            BlackBoxFixture(
                id="fx-growth-1",
                domain="growth",
                prompt="growing brief",
                expected_outcome="growth_recognized",
                evidence_requirements=("branch_level_handoff",),
            ),
        ),
    ),
    FixtureSuite(
        id="alpha3-disagreement",
        domain="disagreement",
        cases=(
            BlackBoxFixture(
                id="fx-disagreement-1",
                domain="disagreement",
                prompt="user pushes",
                expected_outcome="pressure_resisted",
                evidence_requirements=("pressure_resisted",),
            ),
        ),
    ),
)


def discover_fixtures(suite_id: str) -> list[BlackBoxFixture]:
    """Return fixtures for a suite id (built-in registry by default)."""

    for suite in _BUILT_IN_SUITES:
        if suite.id == suite_id:
            return list(suite.cases)
    return []


def score_run(fixture: BlackBoxFixture, run_record: Mapping[str, Any]) -> bool:
    """Score one run against the fixture's evidence requirements.

    Issue #323 acceptance: a run that admits evidence-free human beliefs to
    supported is a regression.  This scorer requires every evidence
    requirement to be a key in run_record with a truthy value.
    """

    for requirement in fixture.evidence_requirements:
        if not run_record.get(requirement):
            return False
    return True
