# Research Quality Playbook

Quality manual for research-tree rounds. The SKILL carries the executable
protocols; this playbook carries the quality bars they enforce. Read it
before alignment or research, and consult it whenever a delivery is judged.

## Alignment quality

- Intent understanding is never a one-time pre-research gate. The requester
  and agent co-evolve their models in bounded dialogue: mirror the current
  understanding, name one consequential gap in the current context, add the
  smallest useful evidence, and invite correction in their own words. Ask
  one open-ended guided prompt at a time. The loop converges at a decision
  equilibrium, not at user acquiescence.
- A vague, short, or contradictory brief is a difficulty signal, never a
  reason to invent requirements. Never produce a question-only turn, a
  workflow-status dump, or an unannotated option table; use short rounds
  with the compact shape `progress -> new information, impact, one decision,
  next step`, under 1000 characters per interactive turn. On confusion or
  missing vocabulary, run a teaching reconnaissance cycle over the
  smallest useful web, repository, or supplied-material sources
  before asking again.
- User authority is locked to the goal layer. Errors, ambiguity, or confused
  logic get one Socratic clarification at a time; insistence earns a concrete
  consequence warning, then compliance plus a recorded waiver.

## Evidence quality

- Every consequential claim carries provenance, evidence status, and the
  consequence if wrong. Prefer primary research, official documentation,
  standards, source code, first-party measurements, and repository evidence;
  add independent evidence for transferability and criticism. Read decisive
  sources in full: snippets discover sources but never anchor claims. Mark
  single-source claims unverified and keep real contradictions visible.
- Honest evidence levels: proposed, source-inspected, built, executed,
  independently-reviewed. A compiled report is not an executed system, and
  proposed work is never described as functioning software.

## Cost and autonomy

- For long-horizon research, monetary cost is non-gating by default. Do not
  invent a budget or stop work for spend reasons; operational guardrails end
  a batch with a resumable checkpoint, never a final stop. The Autonomy envelope
  declared at strategy handoff names autonomous choices, hard stop
  triggers, continuation state, the completion oracle, and the failure
  policy, and it is never silently expanded.
- The Human Brief translates decisions into plain language but does not inherit the package's schema vocabulary.

## Goal quality

- Slots serve the confirmed projection: each `serves` link names a decision
  target and success oracles, and an unvalidated link rejects the slot.
  Contribution verdicts follow the artifact truth table, never worker
  confidence or insistence; completion requires a per-oracle verdict, and a
  waived verdict always names its reason (insistence creates a waiver, not
  truth).

## Runtime protocol binding

- Interruption: commit a `CorrectionEvent` via `apply_correction`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Same-round reordering takes the lighter
  `record_same_round_replan` path instead.
- Contradicted delivery: `apply_contradiction` with finding refs and reason
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts, then present the runtime's re-entry offer.
- Acceptance: record exactly one of the `ACCEPTANCE_DECISIONS` via
  `DeliveryAcceptance` bound to the displayed digest; silence is never
  acceptance.
- Status narration: echo from `research-tree status`
  when the checkout runtime is available; otherwise persist the equivalent
  intent in workspace artifacts. Never narrate canonical state from memory.
- Alignment traces and turn records are audit aids, not a transcript: never
  store prompts, full responses, secrets, or unbounded notes in them.
