# Paired Pilot v1 — Execution Instructions

Reproducible procedure for one pilot execution (both arms, all cases).

## Setup

1. Pin the environment: one model (manifest `model.id`, identical revision
   both arms), one host (`claude-code`), manifest `seed`.
2. For each arm, check out its commit (manifest `arms`): A1 at `0.0.1-a1`,
   A2 at the recorded dev commit. Build the arm's package from that checkout:
   `uv run python scripts/build_skill_packages.py`.
3. Per case per arm, create a fresh isolated workspace (empty directory with
   the case's repository/materials only). No state may cross cases or arms.

## Per case per arm

1. Install the arm's built skill package into the host.
2. Run the case `task_prompt` verbatim. For pp08, deliver the scripted
   mid-run correction exactly as written in the transcript plan.
3. Capture: full transcript; both deliveries; `research-tree status` and
   `research-tree verify` outputs (A1: the alpha1 equivalents).
4. Record process metrics (rubric-v1.md list) into
   `evaluation/pilot/results/<case>/<arm>.json`.
5. Anonymize outputs to `arm-a`/`arm-b` with a held mapping.

## Scoring

1. One evaluator, blind per rubric-v1.md; scores committed in one pass.
2. Scores land in `evaluation/pilot/results/scores-v1.json`; unblind only
   after commit.
3. Fill `docs/evaluation/research/pilot-report-v1.md` tables from scores +
   process metrics; write the stage-attribution ranking from per-stage arm
   differences only.

## Degraded delivery

If host execution is unavailable, record `not-run` for the affected arms in
the report's execution-status section with the reason. Missing ≠ pass: no
score cells are filled, no comparative conclusions are drawn.
