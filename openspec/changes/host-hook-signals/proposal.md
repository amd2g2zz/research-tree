# Proposal: host-hook-signals

## Why

Host hook commands (`uv run --locked research-tree-hook ...`) depend on the
research-tree uv environment, so in any non-checkout workspace they fail at
the uv layer — before lifecycle_hook's fail-open main() can act (issue #453
defect 1). In parallel, user-input feedback signals (corrections,
interruptions, insights, answers) are never captured: `UserPromptSubmit` is
absent from the hook templates, the hook runtime, and `HOST_EVENTS`, so the
only correction path is agents remembering to call `apply_correction`
(issue #453 defect 2). The signal waste compounds: a requester's most
valuable steering input evaporates unrecorded.

## What Changes

- NEW `scripts/lifecycle_hook_launcher.py`: stdlib-only fail-open launcher
  that runs with system Python, requires no uv, no venv, and no project
  context. It locates the lifecycle_hook module (packaged sibling copy or
  `<checkout>/src/research_tree/`) and forwards argv; without a module it
  prints one labeled response and exits 0. lifecycle_hook gains
  fallback flat imports so packaged copies import standalone.
- All three hook templates replace
  `uv run --locked research-tree-hook` with launcher commands ending in
  `|| exit 0`; setup_hooks renders the same launcher command anchored to
  the installed skill directory (`|| exit 0` shell guard included) and
  detects ownership by the launcher filename. `research-tree-hook` console
  script and in-repo usage remain available for development.
- `UserPromptSubmit` is registered for claude and codex; Hermes has no
  user-prompt hook mechanism (N/A, documented). lifecycle_hook accepts the
  event for those hosts and classifies prompts with a heuristic rule table
  (`PROMPT_SIGNAL_RULES`) into
  {correction, interruption, insight, answer, neutral} with high/medium/low
  confidence; only prompts that clearly overturn a prior conclusion or
  instruction rank as high-confidence corrections, and corrections carrying
  continuation semantics are downgraded.
- Signals are recorded append-only under `.research-tree-debug/signals/`
  as sanitized metadata records (category, confidence, rule, prompt
  length, identifiers) — never the prompt text. The directory is capped at
  the newest 200 records; older records are evicted on append. Intermittent
  signals are independent records, queryable by reading the directory.
- High-confidence corrections with an active run context are additionally
  appended to the run's events directory with `route: "apply_correction"`
  for operator and agent inspection; the automated alignment consumer that
  would route them through apply_correction with full ledger context is
  planned v2 work, so nothing reads these records automatically today. The
  hook cannot call `apply_correction` directly (CorrectionEvent requires
  run/task/domain ids, digests, and the ledger revision only the workflow
  has). Without run context, only the signal is recorded (fail-open).
- Packaging: the launcher plus packaged `lifecycle_hook.py` and
  `origins.py` copies ship in all three skill packages (hermes executable
  closure updated), and the host adapters document the launcher so
  skill_setup deploys it.

## Impact

- `scripts/lifecycle_hook_launcher.py` (new),
  `src/research_tree/lifecycle_hook.py`, `src/research_tree/setup_hooks.py`,
  `src/research_tree/skill_setup.py`, `hooks/*.template.*` (codex/claude),
  `scripts/build_skill_packages.py`, `scripts/hermes_executable_closure.json`,
  `skill-src/*adapter*.md`, regenerated `packages/**`.
- Consumers of `plan_setup_hooks`/`setup_hook_status` drop the
  `repository` parameter (commands are launcher-anchored, repository-independent).
- No stored-history migration: new writes only (alpha3 zero-compat ruling).
