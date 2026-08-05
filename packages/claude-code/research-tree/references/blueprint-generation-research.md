# Technical Research Package: Blueprint Generation Loop

## Round and Scope

**Working Brief.** Optimize `research-tree` so that large-scale research over
one or more Context Pack materials produces an agent-actionable technical
blueprint, rather than a long research report or a revival of the retired
recursive evidence DAG.

**Baseline.** The current product already has a Working Brief, Research Strategy,
research tracks, repository reconnaissance, two output artifacts, and a
feedback-to-new-Brief loop. It does not yet make the set of decisions required
for a buildable blueprint first-class. That leaves a failure mode in which the
agent performs substantial research but does not close the design choices an
implementation agent needs.

The follow-up product feedback also exposes a prior modeling error: a Working
Brief cannot stand in for intent understanding. The Context Pack may contain
many heterogeneous materials, and the agent must preserve alternative readings
of what the requester is trying to achieve before it commits to a strategy.

**Constraints.** Research remains autonomous after strategy selection; user
feedback creates a new Working Brief from selected Context Bundles;
repositories are first-class evidence; OpenSpec conversion remains explicit and
downstream; the retired `Frame/Evidence/Cognition` runtime is not a compatibility
target.

## Research Strategy

| Track | Decision to enable | Method | Exit criterion |
| --- | --- | --- | --- |
| Intent understanding | How the agent distinguishes raw material from the current goal it should serve | Context/repository inspection and bounded alignment research | Leading and viable intent interpretations have traceable signals and consequences |
| Research orchestration | How to scale breadth without hard-coding an obsolete path | Production research-agent reports and agent research papers | A bounded, dynamic scheduling model with a clear parallelism rule |
| Evidence to design | How research turns into a technical blueprint rather than prose | Research-writing and decision-record patterns | Every critical design choice has evidence, alternatives, and a reversal condition |
| Repository grounding | How external research becomes a repository-specific implementation plan | Software-agent studies | The blueprint identifies actual change surfaces and validation paths |
| Readiness evaluation | How to prove that an implementation agent can start without rediscovery | Agent-evaluation and coding-agent evaluation work | A layered readiness gate, not a source-count or report-length threshold |
| Cost and complexity | When not to use more agents or a graph | Production agent-engineering evidence | Parallelism is limited to independent, high-value work |

## Findings

### 0. Intent understanding precedes research strategy

The requester may supply a single idea, a contradictory bundle of articles and
drafts, a repository, or all of them. These are signals, not a complete intent
specification. The agent needs a revisable Intent Model that separates explicit
statements from inferred outcomes, success signals, drivers, constraints,
non-goals, and viable alternatives. This is a product-design conclusion from
the current feedback and must be tested in real evaluation rounds; it is not a
claim that an agent can prove a user's private motive.

**Design consequence:** make Intent Understanding and the Intent Model a
first-class stage before the Working Brief. Each consequential research track,
Decision Slot, and final recommendation must retain the intent interpretation
it serves and what would reverse that reading.

### 1. Research requires dynamic decomposition, not a fixed descent tree

Anthropic reports that complex research cannot use a pre-hardcoded exploration
path: the lead plans, delegates independent facets in parallel, synthesizes,
and decides whether to refine or continue. It also reports that indiscriminate
agent expansion creates duplication and high token cost. This supports a
dynamic work portfolio with explicit task boundaries, not a permanent recursive
evidence tree. [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

`DeepResearcher` similarly reports planning, multi-source cross-validation,
reflection when observations diverge, and honest abstention in a live-web
environment. These are evidence for event-driven replanning, not evidence that
a fixed task graph should be the product state. [DeepResearcher](https://arxiv.org/html/2504.03160v1)

**Design consequence:** use a temporary scheduling graph for work dependencies
and an append-only relation view for traceability. Neither is the canonical
user-intent model.

### 2. Parallelism earns its cost only for independent decision work

Anthropic's production account says multi-agent research works best for broad,
independent directions and warns that coding tasks often have fewer genuinely
parallelizable steps. It recommends explicit effort scaling and task contracts
to prevent duplicated or excessive work. [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

`Agentless` found a simple, interpretable localization-repair-validation flow
competitive with more elaborate SWE-agent systems on its reported benchmark.
This does not prove that all research should be sequential; it does show that
orchestration complexity must earn a measurable improvement. [Agentless](https://arxiv.org/abs/2407.01489)

**Design consequence:** fan out only independent research tasks. Serialize
tasks whose answer determines an interface, a repository boundary, or a later
experiment. Allocate effort by decision value rather than a fixed number of
subagents.

### 3. The unit of convergence must be a technical decision

Research reports are compressed evidence, but an implementation agent needs
resolved choices: component boundaries, interfaces, state, permissions,
deployment, tests, migration, and rollout. Architecture-decision research
supports preserving the rationale for consequential decisions, not merely the
final component diagram. [Architecture Decision Records in Practice](https://link.springer.com/chapter/10.1007/978-3-031-70797-1_22)

`STORM` shows the value of assembling a structured outline before composing a
long-form result. For this product, the outline must be a **Blueprint Target**:
a set of decision slots and implementation obligations, not generic report
headings. [STORM](https://arxiv.org/abs/2402.14207)

**Design consequence:** compile a Decision Map before deep research. Research
findings close, conditionally close, defer, or overturn individual decision
slots. Generate the package from the resulting Decision Ledger, not by merging
worker reports.

### 4. Repository tools and validation are part of research, not downstream work

SWE-agent found that an agent-computer interface designed for repository
navigation, edits, and test execution materially affects software-engineering
task performance. [SWE-agent](https://arxiv.org/abs/2405.15793) Therefore a
blueprint is incomplete until it maps design choices to repository surfaces and
has an executable validation path.

UTBoost found that existing coding-agent test suites can accept incorrect
patches, so passing the inherited test suite alone is not a sufficient
readiness signal. [UTBoost](https://aclanthology.org/2025.acl-long.189/)

**Design consequence:** route high-impact uncertainty to a repository
experiment or prototype when feasible. Validate package structure, evidence,
and implementation readiness separately from existing tests.

### 5. Evaluation must measure outcome, grounding, and reliability separately

Anthropic evaluates factual accuracy, citation accuracy, completeness, source
quality, and tool efficiency separately, then supplements automated grading
with human testing. [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
The agent-evaluation literature likewise distinguishes behavior, capability,
reliability, safety, evaluation environment, and metric computation. [Evaluation
and Benchmarking of LLM Agents](https://arxiv.org/html/2507.21504v1)

**Design consequence:** end a round only after critical decisions have an
explicit status and the compiled blueprint passes structural, grounding, and
independent implementation-readiness checks. Sources collected and tasks
completed are telemetry, not completion conditions.

## Recommended Algorithm: Decision-Centric Adaptive Research Loop

```text
Context pack + repository baseline
                |
                v
       Intent Understanding / Intent Model
                |
                v
       Blueprint Target / Decision Map
                |
                v
      Strategy compiler + work portfolio
                |
                v
   independent tasks fan out; dependent tasks wait
                |
                v
    Finding Packs -> Decision Ledger -> replan as needed
                |
                v
        Blueprint compiler -> readiness verifier
                |
                +--> unmet critical decision: schedule targeted work
                |
                +--> all critical decisions closed: two deliveries
```

### Blueprint Target

The coordinator derives a bounded target before deep research. It contains only
the design obligations relevant to the Brief, for example:

- system and repository boundary;
- high-impact architecture and technology choices;
- component responsibilities and integration interfaces;
- data, state, and failure semantics;
- permission, security, and operational boundaries;
- repository change surfaces and migration steps;
- validation, observability, rollout, rollback, and success metrics.

Each obligation becomes a **Decision Slot** with impact, uncertainty,
irreversibility, downstream dependencies, repository touch points, evidence
standard, and a closure rule. The target can be revised by research; it is not a
frozen requirements questionnaire.

### Dynamic Work Portfolio

The coordinator turns uncovered decision slots into small work items. A work
item has one decision question, a clear scope boundary, preferred source or
tool types, a budget, dependencies, output schema, and an exit condition. It
returns a compact Finding Pack rather than prose.

Use a heuristic priority, to be calibrated with real evaluations:

```text
priority = (decision_impact * uncertainty * downstream_leverage * irreversibility
            * expected_decision_value)
           / estimated_cost
```

`expected_decision_value` is an action-selection prior, not measured
information gain. After execution, calibrate it against the persisted evidence
delta and Decision Slot changes.

The scheduler additionally enforces coverage deficits, tool capacity, source
diversity, duplicate suppression, and dependency readiness. It starts with a
small broad landscape and repository pass, then concentrates budget on critical
unclosed decisions. This is a decision policy, not a claim of a universally
optimal mathematical scoring function.

### Finding Packs and the Decision Ledger

Each work item returns atomic observations, source or repository anchors,
applicability conditions, evidence limitations, supported and contradicted
options, implementation implications, and remaining uncertainty. The
coordinator updates the Decision Ledger, where every final design decision
records:

- selected option and meaningful alternatives;
- evidence and repository facts used;
- implementation impact and change surface;
- confidence, assumptions, and reversal conditions;
- required experiment, test, migration, or rollout control.

Events that trigger replanning include contradictory high-quality evidence,
repository facts that falsify an assumption, a failed prototype, an uncovered
critical decision, or budget saturation. Normal evidence-driven replanning is
internal to the round. User feedback that changes the target creates a new
Brief and a new round.

### Blueprint Compilation and Readiness Verification

The compiler renders the two deliverables from the Decision Ledger. The
agent-facing package includes an implementation blueprint with components,
interfaces, state transitions, repository changes, ordered work, validation,
and rollout controls. It does not contain a stitched collection of researcher
subreports.

The verifier applies five gates:

1. **Intent alignment:** the leading Intent Model interpretation, explicit user
   statements, and material alternative readings are traceable to the blueprint
   choices they affect. This checks transparency of interpretation, not access
   to a user's private mental state.
2. **Structural closure:** every critical Blueprint Target slot is selected,
   conditionally selected with a validation task, or explicitly deferred.
3. **Grounding:** consequential claims and decisions point to a repository fact,
   supplied input, external source, or labeled assumption; contradictions have
   a disposition.
4. **Implementation readiness:** a separate agent receives only the package and
   repository baseline, then identifies concrete touch points, interfaces,
   first implementation slice, tests, and blockers. Any rediscovery question is
   returned as a package defect or a new research task.
5. **Operational quality:** an outcome rubric scores coherence, risk coverage,
   rollback, observability, and appropriate tool or budget use. Automated
   checks are supplemented by representative human review.

## Recommended Architecture

```text
Input Registry / Repository Inspector
                 |
                 v
      Context Facts + Intent Modeler + Blueprint Target Compiler
                 |
                 v
 Intent Model / Working Brief / Strategy / Decision Map Store
                 |
                 v
         Adaptive Portfolio Scheduler
                 |
      +----------+-----------+----------+
      v          v           v          v
   web/docs    repo scan   prototype  evaluation
      \          |           |         /
       \---------+-----------+--------/
                 v
        Finding Store + Decision Ledger
                 |
                 v
      Blueprint Compiler + Readiness Verifier
                 |
        +--------+--------+
        v                 v
Technical Research Package  Human Research Report
        |
        +--> explicit request --> OpenSpec exporter
```

The product maintains two deliberately different graph-like views:

- a disposable **work dependency graph**, used only to schedule the current
  portfolio and allowed to change as evidence arrives;
- a versioned **traceability relation view**, linking inputs, findings,
  decisions, repository anchors, and blueprint sections. It may contain
  contradiction and supersession relationships and must not be constrained to
  a one-way recursive tree.

## Evaluation Plan

Build a small, versioned evaluation set from real incomplete briefs, article
packs, and repositories. For each case, collect a human-reviewed Decision Map
and implementation-ready reference constraints. Measure:

| Dimension | Example measure |
| --- | --- |
| Intent fidelity | Explicit signals and viable alternative readings trace to design consequences without being presented as user facts |
| Blueprint closure | Critical decision slots closed or explicitly deferred |
| Grounding | Claim/decision anchors valid and applicable |
| Repository fit | Touch points, dependencies, and tests match the checked revision |
| Implementation readiness | Blind implementer produces a viable first slice without research redo |
| Technical quality | Rubric score for coherence, interfaces, risk, rollout, and reversibility |
| Research efficiency | Cost and latency per materially closed decision |
| Reliability | Contradictions, unsupported decisions, and failed readiness checks |

Start with a small representative set and trace-level inspection. Expand only
after the failure taxonomy stabilizes. Compare the adaptive loop against a
single-agent strategy and a fixed-workflow baseline; otherwise added agents or
graph machinery have no demonstrated value.

## Decision

Adopt the **Decision-Centric Adaptive Research Loop** as the product's core
algorithm. Replace the present track-only scheduling language with a
Intent Model, Working Brief, Blueprint Target, Decision Map, dynamic work
portfolio, Finding Pack, Decision Ledger, and readiness verifier. Preserve
outer Working Brief recursion and use DAGs
only as changeable scheduling or traceability views.
