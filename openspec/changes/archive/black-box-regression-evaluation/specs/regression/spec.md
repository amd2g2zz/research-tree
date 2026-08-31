## ADDED Requirements

### Requirement: black-box regression covers cognition, growth, and disagreement
A FixtureSuite spans the three scenarios from issue #323 acceptance. score_run rejects runs that lack the fixture's evidence requirements.

#### Scenario: evidence-free belief rejected
- **WHEN** score_run(fixture, run_record) and run_record lacks every required evidence key
- **THEN** the score is False (regression)

#### Scenario: parser is whitelist
- **WHEN** parse_fixture loads a JSON file
- **THEN** unknown fields are ignored but missing required fields raise
