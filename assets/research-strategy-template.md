# Research Strategy: {{strategy_id}}

## Technical Outcome

{{The decision or capability this round must enable.}}

## Baseline

{{Repository facts, supplied-material observations, and assumptions.}}

## Context Selection

| Bundle or input | Role | Authority/limitation | Disposition for this round |
|---|---|---|---|
| {{...}} | {{primary|constraint|context|counterexample|baseline}} | {{...}} | {{use|revalidate|defer|out of scope}} |

{{Retain material conflicts as separate signals. State which conflict needs
research, which is scoped by version or audience, and which is carried as an
assumption.}}

## Intent Model

| Interpretation | Signals | Status/confidence | What changes if wrong | Resolution path |
|---|---|---|---|---|
| {{...}} | {{input/repository/alignment refs}} | {{leading|viable|rejected; low|medium|high}} | {{research, blueprint, or implementation effect}} | {{alignment research|repo inspection|prototype|user question only if non-recoverable}} |

{{Separate explicit user statements from agent inferences. Include only the
technical, user, delivery, commercial, or risk drivers that materially affect
this strategy.}}

## Blueprint Target and Decision Map

{{The bounded design obligations that must be closed before implementation can
begin. State the relevant architecture, interface, state, security, migration,
validation, and operational slots.}}

| Priority | Decision Slot | Intent basis | Why it matters | Repository touch points | Closure rule |
|---:|---|---|---|---|---|
| P0 | {{...}} | {{intent hypothesis id}} | {{impact and irreversibility}} | {{paths/symbols or greenfield assumption}} | {{selected, conditional with validation, or deferred with fallback}} |

## Research Tracks

| Priority | Track | Decision slots | Method | Evidence standard | Exit criterion |
|---:|---|---|---|---|---|
| 1 | {{...}} | {{...}} | {{...}} | {{...}} | {{...}} |

## Portfolio Policy

{{Start broad across independent high-impact decisions, then concentrate on
unclosed decisions. State dependencies, duplicate-work exclusions, task budget,
and replan triggers.}}

## Budget and Autonomy

- Time/source/prototype budget: {{bounded default or explicit value}}
- Alignment research before deep research: {{scope}}
- Assumption policy: {{...}}
- User question policy: {{only non-recoverable decisions or explicit co-design}}

## Expected Technical Design Depth

{{Architecture, interfaces, data/state flow, agent/tool loop, security, deployment, evaluation, migration, and implementation tasks as applicable.}}

## Readiness Gates

- Decision closure: {{P0 slots and conditional/deferred policy}}
- Traceability: {{decision -> evidence/repository anchor -> design -> task -> oracle}}
- Repository fit: {{path/symbol/revision and test/deploy anchor checks}}
- Implementation readiness: {{independent package review or implementation slice}}
- Risk tier: {{default|medium|high and required verification}}

## Prior Material Disposition

{{For every relevant prior finding, record reuse, revalidate, downgrade, ignore, or overturn with a reason.}}

## Delivery

- Technical Research Package: {{path or contract}}
- Human Brief: {{path or contract}}
- OpenSpec: {{disabled unless explicitly requested}}
