## Why

The shared loader and activation contracts need adversarial proof. A green
static package test is insufficient if mutation, stale sessions, or implicit
handoffs can still authorize research.

## Scope

Inject faults for Codex, Claude, and Hermes and record deterministic bounded
outcomes. Hermes Docker is an optional host-specific evidence source; it is not
a runtime dependency.

## Non-goals

No runtime feature changes. Defects return to #269 or #270.
