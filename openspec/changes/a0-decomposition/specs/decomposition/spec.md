## ADDED Requirements

### Requirement: the provenance law drops unsourceable elements before persist

Every element carries source = chat message id or attachment id + quote;
unsourceable elements are extractor hallucinations and are dropped (drop
count recorded), not stored.

#### Scenario: unsourceable element dropped
- **WHEN** an extraction contains an element without source (or without quote)
- **THEN** it is absent from the parsed elements and the drop count increments

#### Scenario: one utterance splits into several classes
- **WHEN** an utterance is extracted into both constraints and intents
- **THEN** both classes carry the element with the same provenance

#### Scenario: constraints separate hard from guessed
- **WHEN** constraints carry hardness flags
- **THEN** hard (deployment fact) and guessed are distinguishable per element

### Requirement: the sufficiency checklist is computed and blocks confirmation

All six classes ≥1 (refusals may be explicitly "none"); a difficulty with no
kill-candidate mapping is a pre-registration gap.

#### Scenario: complete set confirms
- **WHEN** all six classes hold and every difficulty maps a kill candidate
- **THEN** confirmation persists the set with status confirmed and checklist complete

#### Scenario: gaps block confirmation
- **WHEN** a class is empty without the explicit refusals "none" note, or a difficulty lacks kill candidates
- **THEN** confirmation is blocked naming the gaps (incomplete sets save as draft)

#### Scenario: re-confirmation is a major pivot
- **WHEN** an already-confirmed decomposition is confirmed again
- **THEN** it is rejected (re-sign belongs to the state machine)
