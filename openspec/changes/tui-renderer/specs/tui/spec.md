## ADDED Requirements

### Requirement: the TUI frame is same-source

#### Scenario: frame renders from the ledger
- **WHEN** a frame renders with claims and transitions in the stream
- **THEN** the frame carries SIDEBAR/PHASE/CLAIMS/CONSOLE sections with the live data

#### Scenario: deterministic
- **WHEN** two frames render from the same stream state
- **THEN** they are identical

### Requirement: red lines carry into the terminal

#### Scenario: uncommitted tasks labeled
- **WHEN** a task has no committed version
- **THEN** its sidebar row carries 未冻结·不可跟踪

#### Scenario: frozen banner
- **WHEN** a task has a committed version
- **THEN** the FROZEN banner shows vN·verdict·truncated-hash with 继续研究=版本+1

#### Scenario: status text always present
- **WHEN** the PHASE section renders
- **THEN** each task carries "phase: <word>" (never color-only)
