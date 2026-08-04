# Research-Tree Architecture

## 1. First principles

Technical research is not a document collection problem. It is a decision
problem under incomplete and potentially contradictory evidence. The system is
complete only when it can show why the important decisions are closed, what
evidence supports them, what could reverse them, and what remains unresolved.

Before handoff, beliefs live in a SQLite-backed temporal heterogeneous
multigraph so human and agent claims, disagreements, evidence, and revisions do
not collapse into one premature interpretation. The research tree begins only
after the confirmed strategy is compiled from that graph. It is therefore an
execution search over decision states, not a topic outline, a dialogue model, a
list of workers, or a report outline.

```text
state_t
  -> choose one verifiable research action
  -> observe source / repository / experiment / user input
  -> normalize observation with provenance
  -> update claims, uncertainty, and decision slots
  -> generate new candidate actions
  -> score, penalize, prune, checkpoint
  -> state_(t+1)
```

The final reports are projections of a closed state. A report generator must
not be allowed to declare completion merely because a wave of workers ended.

## 2. State model

One active run contains five coupled ledgers:

1. **Intent model**: the outcome, scope, authority, environment, and success
   oracle as understood jointly by the requester and the agent.
2. **Decision map**: decision slots, alternatives, impact, uncertainty,
   closure rules, validation oracle, fallback, and reversal condition.
3. **Evidence ledger**: atomic claims, source/artifact references, extraction
   confidence, applicability, counterevidence, and whether a claim changed a
   decision.
4. **Research frontier**: candidate actions that can still change a decision.
5. **Completion ledger**: mandatory evidence classes, negative searches,
   validations, unresolved contradictions, and the reason a slot closed.

An active tree node is a snapshot of these ledgers plus one proposed action:

```text
ResearchNode
  parent_state_ref
  decision_slot_id
  action_kind / action_question
  hypothesis_or_gap
  required_evidence
  validation_oracle
  depth / status
  selection_value (prior, not fact)
  realized_delta (measured after execution)
```

Evidence is a graph-like object even though execution has one active tree.
The same source may support multiple nodes; deduplication must not erase that
provenance.

## 3. Inputs and normalization

All inputs become typed events before they affect the tree:

- documents: claims, citations, version/date, quoted location;
- code/repositories: symbols, commits, call paths, test or execution output;
- images/diagrams: extracted observations, image reference, extraction method,
  and lower default confidence until independently anchored;
- user messages: intent assertions, constraints, corrections, or authority
  grants. A one-line user request is an intent hypothesis, not technical
  evidence.

An adapter may fail or produce ambiguity. That creates an explicit evidence
gap; it does not silently become a fact or a blocker.

## 4. Action value, not fake information gain

Open-ended research normally has no calibrated posterior over all possible
answers. Classic information gain is therefore insufficient as the primary
controller. Keep two separate values:

- `expected_value`: a conservative prior used to choose the next action;
- `realized_delta`: measured from the evidence/decision state after execution.

The initial tree has `realized_delta = 0`. Existing Finding Packs are loaded as
the baseline, so repeated claims or sources have zero realized delta.

The selection prior is decision-oriented. It treats each Decision Slot closure
obligation as a boosting residual and normalizes proposed work by the observed
complexity of the branch that produced it:

```text
closure_deficit = max(evidence_deficit, validation_deficit)
residual_risk =
  decision_impact * unresolved_uncertainty * closure_deficit
  * capped_validation_failure_boost

branch_complexity = 1 + log2(max(1, observed_sibling_count))

selection_value =
  mandatory_gate
  + residual_risk * method_novelty / branch_complexity
  - depth_penalty
  - repetition_or_stagnation_penalty
```

Execution effort can schedule otherwise comparable actions, but it must not
remove required research or satisfy a stop condition. The asymmetric cost that
matters for closure is the consequence of a false decision, represented by
Decision Slot impact and mandatory validation.

After execution, the coordinator measures delta from state changes:

```text
realized_delta =
  new_independent_anchors
  + resolved_contradictions
  + eliminated_alternatives
  + reduced_uncertainty
  + newly exposed high-impact gaps
```

These terms are normalized and recorded separately. A worker's claim that its
answer was informative is never accepted as the measurement. The prior is
calibrated against realized outcomes over later runs; until calibrated, it is
explicitly heuristic.

## 5. What growth means

Growth is a state transition, not adding more workers. A completed action may
grow the frontier in three ways:

1. **Depth growth**: evidence exposes a narrower unresolved question.
2. **Breadth growth**: evidence exposes a competing hypothesis, method, or
   alternative that must be compared.
3. **Correction growth**: evidence invalidates a premise and creates a
   successor branch with a revised intent or decision obligation.

Workers must return atomic findings plus structured `open_gaps`,
`contradictions`, `candidate_methods`, and `validation_requests`. Free-form
prose is not a growth signal. Each generated child records its parent,
triggering evidence, required oracle, and why it can change a decision.

## 6. Pruning and penalties

Pruning changes the active frontier, never historical evidence:

- `closed`: its decision oracle is satisfied;
- `duplicate`: same normalized action and evidence boundary;
- `dominated`: a stronger independent path answers the same question;
- `deferred`: depth/frontier guardrail or temporarily low value;
- `invalid`: the premise was disproved;
- `blocked`: required capability is genuinely unavailable after alternatives.

High-impact contested nodes cannot be pruned solely for low score. They require
an adversarial or validation path. Deferred nodes remain resumable.

Penalties target behavior, not facts: repeated source/query, no ledger change,
unsupported confidence, repeated failed tool attempts, and sibling similarity.
A penalty lowers future selection value or changes the method; it does not
delete the observation.

Validation has three observable outcomes. `passed` removes its closure deficit;
`failed` increases the bounded residual weight and grows an independent-method
retry; `inconclusive` changes method without being counted as either success or
failure. Repeated failure is capped because an impossible or badly specified
oracle must become an explicit blocker, not an infinite boosted loop.

## 7. Stop policy

There are separate batch, slot, and run stops.

- **Batch stop**: persist a checkpoint when the current tool/concurrency slice
  ends. This is resumable and is not completion.
- **Slot stop**: close only when its required evidence classes, counterevidence,
  validation oracle, assumptions, fallback, and reversal condition are present;
  no unresolved contradiction can change the choice.
- **Run stop**: every high-impact slot is closed or explicitly deferred with a
  feasible fallback; no frontier action exceeds the configured value threshold;
  final claim coverage and independent review pass; a final intent audit found
  no material change; and both the Technical Research Package and Human
  Research Report have been verified as deep, persisted artifacts.

When slot closure passes before the two reports exist, persist
`status=delivery_pending`. This is a deliberate non-terminal state: no host
may describe a closed decision ledger as a completed research round. Register
both reports through `tree-deliver`; the runtime records their absolute paths,
UTF-8/no-BOM checks, byte sizes, heading counts, and SHA-256 digests before
entering `complete`.

If a candidate remains above threshold, the system must continue. If all
remaining candidates are below threshold but a mandatory gate is missing, the
run is `blocked`, not complete.

## 8. Persistence and recovery

Each transition appends an immutable `research-tree-state` artifact to the
run's `RunStore`. It references the previous state and all Finding Packs
consumed by the transition. The state stores the active frontier, terminal
reasons, evidence baseline, realized deltas, penalty ledger, and completion
oracle status.

On restart, load the latest state and replay Finding Packs not listed in its
consumed set. Transition application is idempotent by Finding Pack identity.
There is exactly one active tree revision; superseded revisions remain in
lineage for debugging.

## 9. Research basis and limits

Tree of Thoughts demonstrates branch generation, evaluation, and backtracking
for reasoning tasks, while Language Agent Tree Search adds environment feedback
and action outcomes. ReAct supports interleaving reasoning with information-
gathering actions. Bayesian experimental design motivates selecting actions by
their effect on uncertainty, but assumes a model of hypotheses and outcomes
that open-ended technical research usually lacks. These works justify the
control-loop shape, not a claim that an LLM can accurately self-score research
value. The implementation must therefore measure realized ledger changes and
evaluate stop/growth decisions on replayable research cases.

Primary references:

- https://arxiv.org/abs/2305.10601
- https://arxiv.org/abs/2310.04406
- https://arxiv.org/abs/2210.03629
- https://arxiv.org/abs/2302.14545
- https://arxiv.org/abs/2410.17820

## 10. C4.5/C5.0 plus boosting as a research controller

C4.5 and C5.0 are supervised classifiers with known training cases and target
classes. Recursive technical research is an open-world action-selection
problem, so their entropy and error formulas cannot be copied as if research
questions were labeled attributes. Several control principles do transfer:

- **Gain ratio**: C4.5 corrects information gain's preference for attributes
  with many outcomes. The research controller similarly divides residual-risk
  reduction by *observed* branch complexity. A worker that emits many vague
  successors therefore suppresses its own subtree relative to a narrow,
  falsifiable branch. Root Decision Slots are separate obligations and are not
  counted as split outcomes.
- **Missing values**: uncertain observations must remain weighted hypotheses
  or explicit gaps; they must not be forced into one factual branch.
- **Pessimistic pruning**: a non-mandatory subtree whose repeated actions do
  not change evidence or decisions is deferred in favor of its simpler
  parent/fallback. Mandatory closure work is exempt. Research replay data, not
  the C4.5 classification-error formula, must calibrate the threshold.
- **Cost-sensitive classification**: the consequence of a false conclusion is
  asymmetric. High-impact validation remains mandatory regardless of execution
  expense.
- **Winnowing and rulesets**: low-utility evidence dimensions can be removed
  from the active context while retained in provenance; closed tree paths can
  be projected into compact decision rules for delivery.
- **Boosting residuals**: after each transition, closed obligations are
  downweighted and failed validations are upweighted. The next action targets
  remaining weighted decision risk rather than re-running the original broad
  request. This is closer to gradient boosting's stagewise residual correction
  than to majority voting.
- **Boosting caution**: reweighting occurs only after a ledger-observable oracle
  outcome. Worker confidence cannot update the weight. Repeated workers are
  useful only when their evidence and failure modes are sufficiently
  independent; correlated LLM outputs are not multiple votes.

The mapping is deliberately limited:

| Learning-system concept | Research-tree analogue | Not transferred |
| --- | --- | --- |
| training case | Decision Slot closure obligation | a document or topic |
| split | evidence-producing action and its successors | entropy over unknown topics |
| misclassified case | failed or still-open closure oracle | an unpopular conclusion |
| case weight | bounded residual decision risk | worker confidence |
| ensemble round | persisted research transition | a fixed one-wave swarm |
| pruning | defer an unproductive active subtree | deletion of evidence history |

This gives a hybrid controller rather than a literal classifier:

1. initialize every obligation from priority, uncertainty, and closure rules;
2. execute the highest residual-risk actions with method diversity;
3. measure evidence/decision delta and validation outcomes;
4. update bounded residual weights;
5. grow evidence-triggered successors, normalize by actual branching, and
   prune repeated no-change subtrees;
6. stop only when closure oracles pass, not when residual scores merely become
   small.

The official RuleQuest material describes the successor as C5.0/See5, not a
separate C5.2 algorithm. It documents decision trees/rules, boosting,
winnowing, advanced pruning, missing values, and differential costs:
https://www.rulequest.com/see5-unix.html

Boosting references used for the controller distinction:

- Freund and Schapire, *A Decision-Theoretic Generalization of On-Line Learning
  and an Application to Boosting*:
  https://doi.org/10.1006/jcss.1997.1504
- Friedman, *Greedy Function Approximation: A Gradient Boosting Machine*:
  https://doi.org/10.1214/aos/1013203451
- Chen and Guestrin, *XGBoost: A Scalable Tree Boosting System*:
  https://arxiv.org/abs/1603.02754
