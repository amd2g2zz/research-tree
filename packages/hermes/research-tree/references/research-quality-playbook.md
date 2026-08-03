# Research Quality Playbook

Use this playbook with `research-tree`. It defines the operational tests behind
the shorter rules in `SKILL.md`.

## Contents

1. Mutual alignment and feasibility
2. Recursive research loop
3. Claims, sources, and citations
4. Evidence coverage and decisions
5. Experiments and artifacts
6. Multi-agent and context control
7. Report evaluation
8. Heuristic conformance checks
9. Design inspirations

## 1. Mutual alignment and feasibility

The default initial request is exploratory unless the requester explicitly
says to skip discussion and execute. “Exploratory” means the requester may not
yet know the relevant distinctions or decisions, not that their wording is
careless.

```text
initial request
  -> bounded reconnaissance
  -> Blind-Spot Packet + intent rewrite + proposed scope expansion
  -> 1-3 decision-shaped questions
  -> user feedback / correction / delegation
  -> update Living Brief and claim ledger
  -> repeat until provisionally aligned
  -> deep research
```

This is mutual knowledge alignment, not requirement extraction. The requester
can correct the agent. Evidence can correct the requester. The agent can detect
and record its own error. None of those events receives automatic technical
truth status merely because of its origin.

Feedback is also a work signal. "I don't know", "I don't understand", "not
sure", and a correction mean that the current brief needs more knowledge or
verification; they are not refusal, a blocker, or permission to end. After a
concrete correction or failure report, the agent must update the Living Brief
and run a bounded evidence batch before handing control back. A response that
contains only a tree, diagnosis, option table, or proposed fixes is incomplete
when investigation or improvement was requested. Recommendations-only scope
limits edits to the target system; it does not waive research and reporting.

### Authority rules

- User statements control preferences, desired outcome, risk tolerance, and
  authorization when they are explicit. They do not establish that the chosen
  combination of outcome and constraints is feasible.
- User technical claims are hypotheses until supported.
- Agent interpretations and expansions are hypotheses until exposed to the
  requester and tested against evidence.
- Repository observations and experiments are scoped facts, not universal
  truths.
- External claims retain source, version, date, context, and transfer limits.

### Feasibility and constraint consistency

Before producing an implementation-oriented tree, test the relationships among:

- intended outcome and minimum acceptable quality;
- scope and required evidence;
- budget, time, compute, data, labor, and prerequisite assets;
- environment, integration, deployment, and authority boundaries; and
- known physical, technical, economic, logical, legal, or safety limits.

First classify each constraint as `hard`, `preference`, `aspiration`, or
`estimate`. Preserve the wording or dialogue anchor that supports the class.
Do not manufacture infeasibility by treating every desired number as hard, and
do not manufacture feasibility by silently relaxing a hard constraint.

Use current baselines, known bounds, dependency requirements, and simple
order-of-magnitude reasoning. Separate these conclusions:

| Disposition | Meaning | Next action |
|---|---|---|
| `plausible` | No supported material contradiction is known | Continue alignment and research |
| `conditional` | Feasible only if named assumptions hold or constraints change | Expose conditions before proceeding |
| `infeasible` | Hard outcome and constraints cannot be satisfied together | Stop the implementation tree; report the conflict and feasible reframings |
| `indeterminate` | Current evidence cannot decide | Run a bounded feasibility spike with a decisive oracle |

Do not confuse preference authority with reality authority. A requester may
keep an infeasible constraint, but the result is a negative feasibility finding,
not an obligation to invent a plan. Conversely, do not use skepticism as a
shortcut: support an infeasibility conclusion with proportionate evidence,
transparent assumptions, and confidence. If only one constraint appears to
need relaxation, show it; if several trade-offs exist, ask which one the
requester values most.

Nearest feasible reframings are options, not automatic scope changes. Do not
select and elaborate one merely because it is technically attractive. Wait for
the requester to choose or explicitly delegate the changed outcome; an
execute-direct instruction for the original infeasible request is not such a
delegation.

An explicit execute-direct instruction bypasses dialogue, not feasibility
checking. Stop with evidence when the requested combination is infeasible.

### Alignment Checkpoint before action

Before changing the target system, creating implementation artifacts, or running
an irreversible or target-specific experiment, publish one compact Alignment
Checkpoint in the response and Living Brief. It must name:

- the current goal and deliverable;
- scope, non-goals, and the target boundary;
- authority, environment, and permitted actions;
- the success oracle and required evidence level;
- unresolved high-impact Decision Slots and the next 1-3 questions; and
- the current feasibility disposition and assumptions.

This is an inspectable understanding checkpoint, not a ceremonial approval
request. Do not treat silence, "okay", "sounds good", or "continue" as proof
that an unstated requirement is resolved. If a high-impact field remains
unknown or was selected only by the agent, continue bounded reconnaissance and
dialogue. An explicit execute-direct request may use a provisional checkpoint,
but it still requires visible assumptions and does not waive safety, authority,
or feasibility checks. Safe, reversible reconnaissance may continue before the
checkpoint; implementation must wait for it.

### Blind-Spot Packet quality

A useful packet changes the requester's decision position. It must contain some
inspected knowledge, not generic advice generated from memory. It should expose:

- distinctions hidden by the original nouns and verbs;
- missing success or evaluation oracles;
- lifecycle concerns such as long-horizon state, recovery, auditability,
  resource limits, and changing hypotheses;
- target, environment, integration, safety, and operational boundaries;
- plausible adjacent scopes and the cost of including or excluding them;
- an agent-authored intent rewrite and why the expansion is reasonable; and
- the smallest next decisions the requester can now make more intelligently.

Do not dump a universal checklist. Select blind spots that can materially alter
this task. Do not show a detailed branch-specific architecture before the
domain evidence supports it.

Use `ask_user_question` or an equivalent structured tool when available for the
1-3 bounded choices. The surrounding response must first explain evidence,
alternatives, and consequences. If the tool is unavailable, use normal
dialogue. Never encode an unsupported agent default as the recommended option.

### Recursive dialogue and convergence

One exchange is rarely enough for a vague task. Each dialogue turn must do at
least one of these: add inspected knowledge, expose a new consequential blind
spot, test a prior assumption, resolve a disagreement, or sharpen an evidence
criterion. Do not repeat a question merely because it was unanswered.

When a user supplies a concrete pain point after reconnaissance, continue with
the next bounded search, source inspection, or safe experiment before asking
generic preference questions again. Ask only when a consequential,
non-recoverable choice remains. A worker is not blocked until it has searched
available sources, inspected local material, attempted safe alternatives, and
recorded the missing capability or evidence.

Mark the Living Brief `provisionally-aligned` only when:

1. outcome, deliverables, and authorization are mutually understandable;
2. the requester has seen the intent rewrite and proposed scope expansion;
3. material factual disagreements are resolved or have a validation path;
4. success and evidence standards are actionable; and
5. remaining uncertainty does not block the next research decisions; and
6. feasibility is `plausible` or `conditional`, or an `indeterminate` request
   has been reframed as a bounded feasibility investigation.

This is a convergence threshold, not permanent approval. If the requester says
“do not discuss; execute directly,” create an internal provisional frame and
continue without dialogue, while preserving explicit safety and permission
boundaries and reporting assumptions later.

## 2. Recursive research loop

Deep research must continue testing the early problem model:

```text
Living Brief vN
  -> active research tree vN
  -> retrieve / inspect / experiment
  -> atomic evidence and counterevidence
  -> epistemic review
       user claim changed?
       agent claim changed?
       intent/scope/authority changed?
       decision/tree changed?
  -> update Living Brief and the one active tree
  -> continue locally, reopen alignment, or stop
```

### Update classes

| Class | Example | Required behavior |
|---|---|---|
| Local refinement | Evidence changes a recoverable internal design choice | Supersede the active tree revision, log the reason, continue autonomously |
| Material intent/authority change | Evidence exposes a new target, permission, risk acceptance, or success decision | Update the Blind-Spot Packet and reopen dialogue before committing |
| User premise contradicted | Evidence conflicts with a user-supplied technical premise | Present evidence and consequence, preserve the user's decision authority, and ask only if a material choice remains |
| Agent premise contradicted | Evidence conflicts with an agent-selected interpretation or default | Explicitly self-correct, mark the claim refuted, revise intent/scope/tree |

Exactly one research tree is active. Its revision log is a history, not a set of
parallel candidate “latest” trees.

### Reflection record

After every meaningful batch, capture:

- new atomic findings and counterevidence;
- affected user and agent claims;
- Decision Slots opened, closed, or changed;
- intent, scope, and tree effects;
- weak, single-source, contradictory, stale, or uncovered claims;
- whether more work can change a decision; and
- `continue`, `local replan`, `reopen alignment`, or `stop` with a reason.

Stop when decision-specific evidence standards are met and marginal work cannot
change the recommendation within budget. Stop earlier with an explicit fallback
when evidence is unavailable. Do not use certainty as the convergence oracle.
If new evidence changes feasibility, reevaluate the entire active tree and stop
implementation planning rather than preserving it through sunk-cost bias.

## 3. Claims, sources, and citations

Write 2-4 decision-shaped subquestions for every external track. Use 2-3
materially different search formulations and actively seek negative results,
criticism, incompatible versions, and failure conditions.

Prefer:

1. repository evidence and reproducible experiments for the system in scope;
2. standards, primary research, official documentation, source code, release
   notes, and first-party measurements;
3. independent operational evidence for transferability and criticism; and
4. secondary summaries only for discovery or background.

Read decisive sources in full. A snippet is not evidence for a consequential
claim. Record atomic claims with source, version/date/context, applicability,
confidence, limitation, counterevidence, and affected decision. Mark
single-source claims unverified.

Final externally verifiable factual claims require inline links or exact Source
Ledger references. Clearly label user assertions, agent inferences, repository
facts, external claims, and experiment results.

## 4. Evidence coverage and decisions

Tracks organize work; Decision Slots determine convergence. For every
high-impact slot define:

- intent or claim basis;
- impact, uncertainty, and irreversibility;
- alternatives and counterevidence sought;
- required source classes or experiment;
- repository or environment anchors;
- closure rule and validation oracle;
- fallback and reversal condition.

Use `bounded`, `standard`, or `deep` depth. A source count is a budget, never a
depth score. A slot is `selected`, `conditional`, `deferred`, or `blocked`; an
open high-impact slot cannot disappear because a track produced prose.

## 5. Experiments and artifacts

For a testable consequential claim, define:

- baseline and environment;
- one hypothesis and coherent change surface;
- metric or oracle;
- fixed time/iteration budget;
- regression or safety guard;
- raw command/result location; and
- keep/discard outcome.

Never keep an apparent improvement whose guard fails. Preserve negative and
inconclusive results.

Assign each requested output one level:

| Level | Meaning |
|---|---|
| `proposed` | Report, design, schema, pseudocode, or unexecuted plan |
| `source-inspected` | Decisive external/repository evidence inspected |
| `built` | Representative artifact successfully constructed |
| `executed` | Artifact run against a stated oracle with raw evidence |
| `independently-reviewed` | Separate review or replication completed |

File existence, a report build, or a proposed command does not establish a
working product. When usable, actual, validated, or buildable output is
requested, execute the smallest representative artifact unless blocked by
safety, permission, environment, or cost. State the blocker and missing
evidence without upgrading the level.

## 6. Multi-agent and context control

Delegate only independent Decision Slots. Give each worker a bounded question,
source boundary, budget, expected Finding Pack, and completion rule. Workers
return atomic findings, applicability, evidence, counterevidence, decision
effects, and remaining uncertainty, not final-report chapters.

The coordinator owns the Living Brief, active tree, contradiction checks,
deduplication, evidence coverage, epistemic review, and final synthesis.
Compress large finding sets only while preserving every claim's provenance,
limitation, dissent, and affected decision.

## 7. Report evaluation

Fail the package if any of these is true:

- it treats the original wording as a complete specification without
  execute-direct instruction;
- it outputs a research tree or questionnaire without adding inspected
  knowledge;
- it starts implementation, target edits, or irreversible experiments without
  an explicit Alignment Checkpoint covering the high-impact fields;
- it treats "I don't know" or a user correction as a stop signal, or ends a
  requested investigation after only proposing fixes;
- it silently chooses a domain, target, user, tool, or architecture;
- it records user correction but not the agent belief that changed;
- it treats user or agent technical statements as authoritative facts;
- it converts mutually inconsistent outcome and constraints into an
  implementation tree without a feasibility disposition;
- it labels a request infeasible from intuition without evidence, or labels it
  feasible merely because the requester insists;
- it freezes alignment after one confirmation despite later contradictory
  evidence;
- multiple trees are presented as current;
- high-impact decisions lack evidence standards, fallbacks, or reversal rules;
- cited sources do not support the claims or are only snippets;
- a report or schema is called an executed product; or
- the Human Brief and Technical Research Package disagree.

## 8. Heuristic conformance checks

Keep evaluation fixtures and their outputs outside the Skill and its runtime
references. Do not copy benchmark prompts, domain nouns, option lists, observed
answers, or run records into these instructions. Test varied unseen domains and
judge these invariant properties:

- **Low-context entry:** reconnaissance contributes inspected knowledge before
  asking for a consequential choice; the agent does not silently specialize.
- **Knowledge-bearing dialogue:** each additional alignment turn either adds
  evidence, exposes a material blind spot, tests a premise, resolves a
  disagreement, or improves a decision criterion.
- **Intent evolution:** the agent labels its rewrite and scope expansion, and
  incorporates later user feedback without erasing prior context.
- **Mutual fallibility:** user technical claims and agent hypotheses retain
  provenance and can both be corrected by evidence.
- **Constraint stress:** conflicting outcome, quality, budget, time, or
  environment constraints produce an evidence-backed disposition before any
  implementation tree; infeasible cases yield reframing choices rather than
  ceremonial plans.
- **Action gate:** no implementation or target mutation starts before the
  Alignment Checkpoint names the goal, scope, authority, success oracle,
  unresolved decisions, and feasibility; silence or a generic acknowledgement
  does not close the gate.
- **Recursive execution:** new evidence updates claims and the one active tree;
  material human choices reopen dialogue while local refinements do not.
- **Explicit execution:** an unambiguous instruction to execute bypasses
  discussion but not evidence, authorization, safety, or assumption reporting.
- **Delivery integrity:** the final package is decision- and evidence-complete,
  and never promotes a report or proposed artifact to executed status.

Rotate domains, wording, information order, and contradiction timing during
forward tests. A response that matches a memorized outline but fails these
properties does not pass.

## 9. Design inspirations

- [Deep Research Skills](https://github.com/Weizhena/Deep-Research-skills):
  structured fields, deep execution, schema validation, resumable batches, and
  synthesis.
- [Deep Research Agents: A Systematic Examination and Roadmap](https://arxiv.org/abs/2506.18096):
  dynamic planning, multi-hop retrieval, tool use, architecture taxonomy, and
  evaluation limits.
- [ECC Deep Research](https://github.com/affaan-m/ECC/blob/main/.agents/skills/deep-research/SKILL.md):
  subquestions, varied searches, full-source reading, citations, source quality,
  cross-checking, and explicit gaps.
- [Open Deep Research](https://github.com/langchain-ai/open_deep_research):
  clarification, researcher/supervisor separation, reflection,
  provenance-preserving compression, and report evaluation.
- [Autoresearch](https://github.com/karpathy/autoresearch): fixed budgets,
  comparable metrics, narrow trials, guards, and keep/discard loops.
- [Codex Autoresearch](https://github.com/leo-lilinxiao/codex-autoresearch):
  explicit parsers and guards, append-only audit events, reproducible histories,
  exact failure state, and reversible trials.

Adapt mechanisms rather than copying whole workflows. Open-ended research needs
multi-dimensional convergence, dynamic problem revision, and human-agent
knowledge alignment; it must not inherit an unbounded optimization loop or a
single numeric completion oracle.
