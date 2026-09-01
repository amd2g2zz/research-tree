# Behavioral Layer Specification — Rewrite Deltas

## ADDED Requirements

### Requirement: The forced-load SKILL body stays within the line and word budgets

The skill authoring source `skill-src/SKILL.template.md` MUST stay at or under
300 lines, and the forced-load doc set (`skill-src/SKILL.template.md`,
`skill-src/claude-adapter.md`, `skill-src/codex-adapter.md`,
`skill-src/hermes-adapter.md`, `references/research-quality-playbook.md`) MUST
stay at or under 5,000 words in total, so each research session's mandatory
behavior layer fits the throughput budget.

#### Scenario: Budgets hold after an edit

- **WHEN** the contract suite runs against the repository
- **THEN** `test_skill_template_line_budget_300` measures SKILL.template.md at
  or under 300 lines
- **AND** `test_forced_doc_word_budget_5000` measures the five forced-load
  docs at or under 5,000 words in total.

### Requirement: The slot-only dispatch contract MUST be verbatim in every dispatching doc

The two anchor sentences MUST appear verbatim in SKILL.template.md and all
three host adapters: "only the Decision Slot, its source boundary, stop
condition, and Finding Pack schema" and "MUST NOT receive the strategy
projection digest, primary goal text, or other slots". The anchors are the
contract test's grep targets: changing the wording changes the test.

#### Scenario: Anchors present in all four dispatching docs

- **WHEN** `test_slot_only_dispatch_contract_present` scans SKILL.template.md
  and the three host adapters
- **THEN** both anchors are present in each of the four documents.

### Requirement: Every runtime-API mention MUST carry the checkout availability gate

Every behavioral-doc runtime-API mention MUST carry the checkout availability
gate in adjacent context (two lines before through three lines after): each
`apply_correction`, `apply_contradiction`, and `research-tree status` mention
must be followed closely by the phrase "when the checkout runtime is
available" and the otherwise-branch ("otherwise persist the equivalent intent
in workspace artifacts"), so the installed-package context has zero
unexecutable mandates.

#### Scenario: Gates near every mention

- **WHEN** the gate test scans the behavioral docs plus the hermes host
  template
- **THEN** every runtime-API mention has the gate phrase within its window
- **AND** a mention without a nearby gate fails the test.

### Requirement: Doc-cited runtime APIs MUST exist in src

Every runtime API the behavioral docs cite by name MUST exist in the runtime:
the legacy set (`apply_correction`, `apply_contradiction`, `DeliveryAcceptance`,
`ACCEPTANCE_DECISIONS`, `record_same_round_replan`, `CorrectionEvent`,
`research-tree status`) and the #441-#443 surface (`strategy
propose/display/confirm` CLI verbs, `write_goal_satisfaction`,
`latest_confirmed`, `assess_goal_contribution`, `validate_falsifiability`).

#### Scenario: Doc names resolve

- **WHEN** `test_doc_names_only_real_runtime_apis` runs
- **THEN** every cited name resolves to a real symbol or CLI verb in
  src/research_tree.

### Requirement: Packages MUST regenerate from skill-src

Host packages MUST regenerate from the canonical skill-src/references inputs
via `build_skill_packages.py`, committed separately (generated-only commit),
so the packaged behavior layer stays byte-identical to the authoring source.

#### Scenario: Package check passes

- **WHEN** `build_skill_packages.py --check` runs after the source change
- **THEN** no packaged file is stale and the exit code is 0.
