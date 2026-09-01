# host-hook-signals Specification Delta

## ADDED Requirements

### Requirement: Hook commands run without uv anywhere

Every hook command in the codex and claude templates, and every command
rendered by setup_hooks, SHALL invoke the self-contained launcher
`scripts/lifecycle_hook_launcher.py` with system Python. Commands SHALL
NOT contain `uv run` or `--locked`.

#### Scenario: Launcher fires outside any checkout

- **WHEN** the launcher runs with any system Python in a workspace that is
  not a Research Tree checkout
- **THEN** it exits 0, prints exactly one balanced labeled host response,
  writes no files, and emits no error output

#### Scenario: Broken payload still exits zero

- **WHEN** the hook payload is not valid JSON or the observer raises
- **THEN** the launcher still exits 0 with one labeled host response

### Requirement: UserPromptSubmit is registered where hosts support it

The claude and codex templates and setup_hooks SHALL register a
`UserPromptSubmit` hook wired to the launcher. Hermes SHALL record this
requirement as N/A because Hermes has no user-prompt hook mechanism.

#### Scenario: Templates register the prompt hook

- **WHEN** the codex and claude templates are inspected
- **THEN** each contains a UserPromptSubmit entry whose command references
  the launcher and ends with `|| exit 0`

#### Scenario: Hermes is N-A

- **WHEN** the hermes template is inspected
- **THEN** no UserPromptSubmit entry is present and no uv dependency exists

### Requirement: Prompt signals are recorded as sanitized queryable records

lifecycle_hook SHALL classify UserPromptSubmit prompts with the heuristic
rule table into correction, interruption, insight, answer, or neutral, and
SHALL record each classified signal append-only under
`.research-tree-debug/signals/` as sanitized metadata (category,
confidence, rule, prompt length, opaque identifiers). The raw prompt text
SHALL NOT be persisted. Signals are independent records: intermittent
capture is acceptable and each record is queryable by reading the
directory.

#### Scenario: Correction signal lands on disk and reads back

- **WHEN** a UserPromptSubmit payload carries a high-confidence correction
  prompt inside a checkout
- **THEN** one signal record with category correction, its confidence and
  rule is written under `.research-tree-debug/signals/` and contains no
  prompt text

#### Scenario: Intermittent signals stay independent

- **WHEN** several UserPromptSubmit events fire over a session
- **THEN** each classification produces its own append-only record

### Requirement: Correction signals are fail-open and never write canonical state

The hook SHALL NOT call apply_correction directly: a valid CorrectionEvent
requires run, task, and domain identifiers, artifact digests, and the
ledger revision that only the workflow holds. When a high-confidence
correction fires with an active run context, the hook SHALL append a
signal record marked `route: "apply_correction"` to the run events
directory so the alignment step consumes it with full ledger context.
Without an active run, only the standalone signal record is written. Any
classifier or recorder failure SHALL NOT affect the host session: the
lifecycle hook keeps its fail-open main() and the launcher exits 0 with a
single labeled host response.

#### Scenario: Run-scoped feed with active run

- **WHEN** a high-confidence correction fires and the reported workspace
  has an initialized run manifest
- **THEN** a run-scoped record with route apply_correction is appended to
  the run events directory

#### Scenario: No run context records the signal only

- **WHEN** a high-confidence correction fires without run identifiers
- **THEN** no run events are written and the standalone signal remains
  recorded

#### Scenario: Classifier failure never blocks the session

- **WHEN** any exception occurs during classification or recording
- **THEN** the host receives the normal non-blocking labeled response and
  exit code 0



