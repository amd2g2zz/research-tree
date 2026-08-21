# Typical Research Journeys

Research Tree is useful when the hard part is building enough shared knowledge
to make a defensible decision. The final action may be implementation,
procurement, policy, experimentation, migration, or a deliberate decision not
to act.

Each case below shows the same pattern:

~~~text
messy signals -> shared question -> decision gaps -> evidence -> decision state
~~~

## Case 1: Product And Technical Direction

**Situation:** A team is considering a shared customer-identity capability.
Different stakeholders are already discussing architecture, vendors, staffing,
and deadlines, but they do not agree on the actual decision.

~~~mermaid
flowchart LR
    A[Feature requests<br/>support pain<br/>existing systems] --> B[Outcome and boundary]
    B --> C{Decision map}
    C --> D[User and product need]
    C --> E[Build / buy / defer]
    C --> F[Security and ownership]
    C --> G[Cost and migration]
    D --> H[Evidence ledger]
    E --> H
    F --> H
    G --> H
    H --> I[Selected direction<br/>conditions<br/>validation milestones]
~~~

**Good starting prompt**

> We are considering a shared customer-identity service. Clarify which decision
> we actually need to make, inspect the current systems and constraints, compare
> build, buy, and defer options, and recommend a direction with validation
> milestones. Research only; do not authorize procurement or implementation.

**Knowledge built**

- a shared outcome and explicit non-goals;
- stakeholder, system, data, and ownership boundaries;
- decision criteria that mix product, technical, risk, cost, and delivery
  concerns;
- alternatives with evidence, counterevidence, and missing information;
- conditions that could change the recommendation.

**Deliverable use**

The decision owner reads the Human Research Report. A planning, architecture,
procurement, or implementation agent consumes the Technical Research Package
without treating the recommendation as authorization.

## Case 2: Incident And Root-Cause Research

**Situation:** A release path sometimes publishes stale artifacts. Logs are
partial, prior attempts are inconsistent, and several plausible causes exist.

~~~mermaid
flowchart LR
    A[Logs<br/>receipts<br/>code paths<br/>prior attempts] --> B[Incident timeline]
    B --> C[Competing hypotheses]
    C --> D[Reproduce or falsify]
    D --> E[Observed evidence]
    E --> F{Contradictions?}
    F -->|yes| C
    F -->|no| G[Root-cause position]
    G --> H[Containment<br/>durable fix<br/>recurrence oracle]
~~~

**Good starting prompt**

> Investigate why this release path intermittently publishes stale artifacts.
> Build a timeline, identify competing hypotheses, inspect current code and
> runtime evidence, and falsify alternatives where possible. Separate confirmed
> root cause, likely contributors, and unknowns. Recommend containment and a
> recurrence test; do not deploy changes.

**Knowledge built**

- an evidence-linked timeline;
- explicit hypotheses rather than one early narrative;
- test, runtime, and provenance evidence kept distinct;
- disproved causes and unexplained observations;
- a recurrence oracle that can distinguish the failure from nearby symptoms.

**Deliverable use**

Operators get containment and uncertainty in plain language. A debugging or
implementation agent gets the implicated surfaces, evidence anchors, test plan,
and stop conditions.

## Case 3: Tool Or Vendor Selection

**Situation:** A team must choose among managed search services. Feature lists
are easy to find; fit with privacy, staffing, data shape, cost, and exit
requirements is not.

~~~mermaid
flowchart LR
    A[Candidate claims<br/>requirements<br/>budget<br/>constraints] --> B[Weighted criteria]
    B --> C[Source-backed matrix]
    C --> D[Proof-of-concept questions]
    D --> E[Operational and exit risks]
    E --> F[Recommendation]
    F --> G[Decision conditions]
    F --> H[Fallback and exit path]
~~~

**Good starting prompt**

> Compare these three managed search services for our data shape, privacy
> obligations, latency target, staffing, budget, and exit requirements. Verify
> consequential claims with primary sources, identify what needs a prototype,
> and recommend both a preferred option and a safe decision process. Do not
> contact vendors or purchase anything.

**Knowledge built**

- evaluation criteria derived from the real decision;
- comparable evidence with dates, scope, and confidence;
- the difference between documented capability and tested fit;
- lock-in, operating, and migration risk;
- decision conditions and an exit strategy.

**Deliverable use**

The Human Research Report supports a review meeting. The Technical Research
Package can drive a bounded proof of concept, due diligence, or procurement
checklist after separate approval.

## Case 4: Risky Migration Planning

**Situation:** A durable workflow must move to a new runtime without losing
authority, traceability, recovery, or rollback.

~~~mermaid
flowchart LR
    A[Current system<br/>target runtime<br/>failure history] --> B[Invariants]
    B --> C[Dependency graph]
    C --> D[Migration slices]
    D --> E[Verification gates]
    E --> F[Rollout]
    F --> G{Oracle passes?}
    G -->|no| H[Stop or rollback]
    G -->|yes| I[Promote next slice]
~~~

**Good starting prompt**

> Plan a migration of this durable workflow to the target runtime. First map
> current authority, persistence, recovery, and host boundaries. Identify
> invariants and failure modes, then propose staged slices with verification,
> observability, rollback, and ownership. Do not create an implementation plan
> until the migration decision and safety conditions are explicit.

**Knowledge built**

- current and target boundaries;
- invariants that must survive the migration;
- dependency and sequencing constraints;
- test evidence versus live-environment evidence;
- rollout gates, rollback triggers, owners, and unresolved risks.

**Deliverable use**

Decision owners can approve, defer, or constrain the migration. Downstream
agents receive a staged plan only after the authority and success conditions
are explicit.

## Adapting The Pattern

The same knowledge flow applies to security posture research, policy and
governance design, reliability investment, data architecture, external API
selection, operating-model changes, and research about whether more research is
worth the cost.

A strong prompt does not need to prescribe the research tree. It should state
the real pressure, known constraints, available evidence, authority boundary,
and what a useful decision would enable.
