# Proposal: baseline-freshness-policy

## Why

issue #327 (confirmed): evidence validates identity (anchor matches inspected
revision) but not freshness. A stale baseline that touches implementation-relevant
paths must trigger revalidation, scoped block, or explicit historical-analysis
disposition. Offline/unreachable authority becomes freshness_unknown — not
silently current, not globally blocked.

## What Changes

1. `src/research_tree/freshness.py`: `FreshnessPolicy` (authorized remote/ref,
   allowed ahead/behind, relevant paths, historical-analysis flag),
   `BaselineFreshness` admission record (inspected/authority commit,
   observed_at, ahead/behind, relevant_path_changes, policy echo,
   disposition), `assess()` pure decision with documented precedence:
   offline → freshness_unknown; explicit authorization → historical; divergent
   + overlap → stale_relevant; divergent + no overlap → stale_irrelevant;
   in-range + overlap → stale_relevant; else current.
2. Intake wiring: `RepositoryInspector.__init__` accepts optional
   freshness_policy; inspect payload gains `freshness` field when provided
   (None preserved when omitted — backward compat byte-identical).
3. Prefix-overlap policy matching (`src/` covers `src/coordinator.py`).
4. tests/test_baseline_freshness_policy.py: 11 tests, one per acceptance
   line + edges + intake integration.

## Impact

- src: freshness.py (new), intake.py (policy arg + payload field)
- Zero behavior change when no policy given; intake payload schema gains an
  optional field, not a required one.
