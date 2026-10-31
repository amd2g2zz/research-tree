# design — early-termination-variant-search

searchVariants filters candidates by dag_still_stands (the candidate declares
whether the kill-graph DAG stands with the variant applied — the declaration
is mechanical: the DAG topology check). buildInquiry presents the evidence
summary + standing variants + the three choices, never a verdict. resolveBury
appends an engine fact (provider.action) and returns the NO-GO recommendation.

## impact_scope

As proposal. GitNexus: new module, no upstream callers.

## rejected_designs

- LLM-judged variant viability (mechanical DAG check).
- Auto-bury on refutation (the question is not the verdict — the user decides).
- Final verdict at bury (the verdict happens at freeze, per A6).
