# Hermes Delivery Phase

Load this file only when synthesizing or auditing final deliverables.

## Technical Research Package gate

The package must be a detailed implementation input, not a briefing note. It
must include:

- evolved intent, scope, non-goals, authority, environment, and success oracle;
- research method, source-selection boundaries, and limitations;
- decision-oriented findings with precise citations and applicability;
- counterevidence, contradictions, rejected alternatives, and uncertainty;
- architecture or operational decisions and their rationale;
- concrete implementation consequences, interfaces, dependencies, migration
  concerns, security boundaries, and failure handling;
- validation strategy with measurable acceptance evidence;
- evidence ledger and exact status of experiments and artifacts; and
- open questions that remain genuinely unresolved.

Separate repository observation, external-source claim, experiment result,
agent inference, and proposal. Never describe a report, generated code, or
successful compilation as an executed production system.

## Human Research Report gate (Human Brief artifact)

The requester-facing report is co-primary and must remain professional,
evidence-bearing, and decision-capable rather than becoming a shallow summary.
In plain language explain:

- the question now being solved and how it changed;
- the few findings that materially changed the direction;
- the recommended strategy and why;
- meaningful alternatives and trade-offs;
- remaining uncertainty and risk;
- what was actually produced or tested; and
- the next implementation decision, if one remains.

Keep it short enough to read in chat and avoid protocol jargon. Do not remove
important uncertainty to make it reassuring. If the requester says the brief
is unclear or the package lacks depth, reopen the relevant decision slots and
run another evidence-bearing batch.

## Final audit

Before delivery verify citation reachability, claim-to-source support,
artifact paths and hashes, decision coverage, contradiction disposition,
feasibility consistency, and the completion oracle. Report unavailable tests
or evidence explicitly.
