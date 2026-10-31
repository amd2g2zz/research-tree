# design — evsi-actions

Selection = argmax(EVSI/cost) within the priority pool. Pool = make-or-break
claim candidates when any exist (early kill saves the most), else all
candidates. Zero-cost candidates raise EVSIError (degenerate winners).
Replay: the full scored candidate table with the hindsight-best disclosed —
次优差距可复盘.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- Absolute-EVSI ranking (ignores cost — the docs mandate the unified ratio).
- Silent zero-cost acceptance (degenerate argmax).
- Opacity (replay disclosure is the issue's acceptance).
