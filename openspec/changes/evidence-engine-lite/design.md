# design — evidence-engine-lite

Evidence rows ride the #547 claims surface (`ev-<claim>-<source>` ids) — no
new tables. Reliability weighted vote: support weight vs refute weight over
source reliability; posterior = support/(support+refute). Independence
collapse: a source whose provenance cites another listed source's origin is
a citation — dropped in favor of the root.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Bayesian full posterior update (needs calibration data — T4).
- URL-prefix dedup (near-duplicate claims pass; provenance-based citation
  collapse is the honest dedup).
- LLM-judged conflict detection (mechanical verdict comparison).
