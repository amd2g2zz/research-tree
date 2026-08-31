---
name: search-algorithm-pattern
description: How to structure research-tree subagent work as goal-conditioned search with ReAct + Reflexion + targeted backtrack + escalation. Use when a subagent receives a task and must execute it adaptively rather than mechanically.
license: MIT
compatibility: research-tree + Claude Code subagents
metadata:
  author: research-tree maintainer
  version: "1.0"
  generatedBy: "alpha4 design phase"
---

# Search Algorithm Pattern for research-tree Subagents

research-tree subagents (custom `.claude/agents/<name>.md` definitions) must
NOT execute tasks as **plan-then-execute** pipelines. A static plan produced
before any evidence is brittle; it cannot recover when an assumption is
invalidated mid-execution (which is the norm in research-tree's batch-1/2/3
fixup flow — wave 0/1/2 produced 2 regressions only caught by wave 3).

Instead, treat every subagent invocation as **goal-conditioned state-space
search**, where:

- **Goal** = the success criteria + drift signals (from openspec acceptance
  criteria, ADR-002/006/007 constraints, or task `Closes #N` body)
- **State** = current files + tests + ledger snapshot + gitnexus context
- **Transitions** = concrete tool calls (Read, Grep, Bash, Edit, git
  checkout, pytest, gh pr)
- **Cost** = tokens + latency + risk of breaking dev branch

The search algorithm below is the implementation. Subagents that follow it
produce higher-quality output with less main-agent intervention.

## The Pattern: ReAct + Reflexion + Targeted Backtrack + Escalation

### 1. ReAct — Interleave Reason + Act

Every step has three parts, in order:

```
Thought:  What does the current state tell me? What is my next goal-aligned step?
Action:   The concrete tool call (Read file X, Run pytest, Grep for Y).
Observe: The literal result. Do not paraphrase — copy the key lines.
```

After `Observe`, decide one of:
- **Continue** — Thought's hypothesis holds → next Thought/Action
- **Revise** — Hypothesis partially holds → adjust ONLY this step, continue
- **Backtrack** — Hypothesis was wrong → return to last known-good state, replan
- **Escalate** — Cannot proceed after 3 consecutive Backtracks → stop, report

### 2. Reflexion — Self-Reflect on Failures

When an `Action` produces an unexpected `Observe` (test failure, file
missing, error code), write a one-line reflection to memory BEFORE the
next `Thought`:

```
Reflection: pytest failed with "ModuleNotFoundError: research_tree".
My prior Thought assumed src/ is on PYTHONPATH. It is not in this test
context. Next Thought: check pyproject.toml pythonpath config.
```

Reflections are written to:
- the subagent's `memory: project` directory if it has one, OR
- a session log file (e.g. `.claude/logs/<agent>-<timestamp>.md`) if not

This prevents **State amnesia** — the failure mode the Loop Engineering
literature warns about for long-running loops.

### 3. Targeted Backtrack — Local, Not Global

NEVER restart from the initial plan after a failure. Backtrack **only the
step whose assumption was invalidated**. The next `Thought` should
explicitly name what changed:

```
Thought (revised): My prior Thought assumed package_data covers nested
JSON files. Setuptools actually requires glob patterns. Next Action:
verify by inspecting the built wheel contents.
```

This is the opposite of the brittle **plan-then-execute** loop, which
restarts from scratch on any failure.

### 4. Escalation — Stop After 3 Backtracks

After **3 consecutive** Backtrack steps without progress, the subagent must
**stop and escalate** to the main agent. The escalation payload is:

```
BLOCKER REPORT
==============
Goal: <success criteria>
State: <last known-good state>
Backtrack history (last 3):
  1. <what assumption failed + evidence>
  2. <what assumption failed + evidence>
  3. <what assumption failed + evidence>
Hypotheses I cannot test without:
  - <tool/permission/info needed>
Recommended next step: <main agent action>
```

Do NOT loop indefinitely. research-tree's batch-2 history shows loops waste
~30% of subagent runtime without producing new evidence.

## What "Goal-Conditioned" Means in research-tree

For a subagent invoked with `Fix issue #N where acceptance is X`:

1. **Pull the Goal from the issue body** — `gh issue view N --repo ...`
2. **Read the acceptance criteria as search goals** — often a checklist in
   the issue, openspec change, or PR template
3. **Read ADR-002/006/007** — these are **non-negotiable constraints**, not
   guidance. A solution that violates ADR-002 (e.g. duplicate completion
   authority) fails the search regardless of test pass
4. **Treat the existing test suite as a **partial** goal test** — passing
   tests do not prove the goal is met. Add new tests that prove the
   acceptance criteria specifically
5. **Treat `pytest` results as Observations, not Goals** — tests are how
   you observe state, but the goal is what the user asked for

## Common Failure Modes This Pattern Prevents

| Failure | What the pattern does instead |
|---|---|
| Plan-then-execute stuck on first error | ReAct's revise step adjusts locally |
| Subagent context window fills with retries | Reflexion writes short memory, not full history |
| Subagent restarts from scratch repeatedly | Targeted backtrack revises single step |
| Subagent reports "done" with green tests but goal unmet | Goal-conditioned: goal is acceptance, not test pass |
| Subagent loops 10× on same failure | Escalation after 3 backtracks hands off cleanly |

## Anti-Patterns to Avoid

1. **No Goal in first Thought** — every subagent invocation MUST restate
   the goal from the issue/spec within the first 2 Thoughts
2. **Action without Observation** — never skip reading the actual output
   of a tool call; do not infer results
3. **Backtrack that rewrites history** — use `git checkout <file>` to
   undo a single Edit, do NOT `git reset --hard`
4. **Escalation without blocker report** — never escalate empty-handed;
   always include the 3-backtrack history
5. **Skipping the research-tree-specific constraints** — ADR-002 single
   completion authority, ADR-006 single scheduling entry, ADR-007 pydantic
   boundary. These are part of the Goal, not optional guidance

## How to Invoke This Pattern

When dispatching a research-tree subagent (via main agent prompt), include:

```
Use the search-algorithm-pattern skill (read .claude/skills/search-algorithm-pattern/SKILL.md).
Goal: <acceptance criteria from issue #N>
Constraints: ADR-002 + ADR-006 + ADR-007 must not be violated.
Search budget: max 3 backtracks before escalation.
```

The subagent's system prompt (in `.claude/agents/<name>.md`) should
reference this skill in its `skills:` frontmatter so it loads at startup.

## References

- Loop Engineering (Requesty, 2026) — four loop types, common failure modes
- ReAct (Yao et al., 2022) — interleaved reasoning + acting
- Reflexion (Shinn et al., 2023) — verbal reinforcement for self-refinement
- research-tree batch-2 meta-arbitration — the empirical evidence this
  pattern addresses (2 of 7 BLOCKING issues were silent-failure regressions
  that plan-then-execute subagents did not catch)
