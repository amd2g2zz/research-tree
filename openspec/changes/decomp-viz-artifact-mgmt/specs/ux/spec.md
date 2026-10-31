## ADDED Requirements

### Requirement: the card wall renders six provenance-visible groups

#### Scenario: provenance on every card
- **WHEN** cards render from a parsed decomposition
- **THEN** each card carries its provenance ("来自你的话" for chat messages, "来自附件" for attachments)

#### Scenario: six classes only
- **WHEN** cards render
- **THEN** the groups are exactly requirements/constraints/background/intents/refusals/difficulties

### Requirement: edit rights before confirm

#### Scenario: delete removes a card from the draft model
- **WHEN** deleteElement removes a requirements card
- **THEN** the card count drops and the confirm proceeds with the reduced set

### Requirement: insufficient elements show placeholders, never demo content

#### Scenario: empty class placeholder
- **WHEN** a class has no elements
- **THEN** placeholderFor names the gap ("待对齐")

### Requirement: checklist gates confirm

#### Scenario: gaps block confirmation
- **WHEN** confirm runs on an incomplete set
- **THEN** it raises naming the pre-registration gap (the incomplete set persists as draft via #549)

#### Scenario: complete set confirms
- **WHEN** confirm runs on a checklist-satisfying set
- **THEN** the decomposition persists as confirmed

### Requirement: deleted nodes land in the frozen version

#### Scenario: deleted_nodes disclosure
- **WHEN** a version freezes with deleted_nodes in the snapshot
- **THEN** the committed version exposes them (产物删除 auditable)
