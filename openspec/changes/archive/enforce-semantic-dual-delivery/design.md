## Context

The canonical compiler already derives a Technical Research Package and a human-facing artifact from one immutable ledger snapshot, but the latter is still named Human Brief and completion does not have a reusable semantic acceptance contract. Host adapters may still rely on Markdown shape or generic acknowledgement. Alpha2 needs both rendered surfaces to remain co-primary, revision-bound products whose consequential claims resolve to canonical decisions, findings, evidence, and validation.

## Goals / Non-Goals

**Goals:**
- Emit `human-research-report` for new delivery revisions while retaining an explicit read-only legacy alias.
- Bind both surfaces to one DeliveryManifest containing exact revisions, source digest, output digests, claim lineage, and depth assessments.
- Validate professional depth, P0 closure, claim traceability, and implementation boundaries without prose-length proxies.
- Model acceptance, partial acceptance, rejection, correction, and withdrawal against the exact displayed pair and route corrective feedback to successor work.
- Keep dual artifact writes atomic on the canonical ledger path.

**Non-Goals:**
- Setting fixed report lengths or mandatory Markdown headings.
- Allowing worker prose or host adapters to decide canonical completion.
- Implementing documentation governance, migration cutover, or release evaluation.

## Decisions

1. Add a focused `acceptance` module with pure validators and an immutable `DeliveryAcceptance` value object. This keeps semantic policy independently testable and reusable by later coordinator work. Embedding it in the renderer was rejected because rendering format must not become the semantic oracle.
2. Treat Technical Research Package and Human Research Report as one manifest-bound pair. Both copies of the manifest must be canonically equal and optional rendered bytes must match their recorded SHA-256 values. Independent manifests were rejected because they permit revision drift.
3. Use typed claim classes and a fixed nine-dimension depth rubric. Facts require evidence/oracle lineage, inferences require both evidence and reasoning lineage, recommendations require decisions and implementation boundaries, and unknowns/limitations require evidence or next validation. Counts, headings, and URL density are deliberately excluded.
4. Rename only the new write surface. `HUMAN_REPORT_KIND` and `human_report` become canonical; `HUMAN_BRIEF_KIND` and `human_brief` remain compatibility aliases for reads/callers during migration. A legacy kind can never satisfy semantic acceptance.
5. Preserve atomicity by validating both payloads before the existing ledger batch append. Acceptance is a separate exact-revision record and cannot retroactively mutate delivery artifacts.
6. Route acceptance outcomes deterministically: accepted completes; target/scope/intent corrections create a successor round; depth/evidence/method/applicability rejection resumes same-round research; presentation-only partial acceptance awaits another explicit acceptance.

## Risks / Trade-offs

- **Compatibility aliases can obscure migration debt** -> Keep canonical constants and fields primary, mark aliases explicitly, and test that new artifacts never use the legacy kind.
- **Semantic validation cannot infer every consequential sentence** -> Require a compiler-produced claim index and validate known structured consequential surfaces; later compiler evolution can add selectors without changing digest rules.
- **Strict exact-key schemas can constrain evolution** -> Version manifest and acceptance schemas and preserve immutable prior revisions.
- **Acceptance feedback might be misclassified** -> Use closed classifications and observable lifecycle actions; reject generic acknowledgements.

## Migration Plan

1. Publish versioned schema changes and the semantic acceptance module.
2. Switch new compiler writes to `human-research-report`, retaining explicit legacy read aliases.
3. Run focused compatibility, lifecycle, schema, and fault-injection tests.
4. Roll back the new write/acceptance path as one unit if needed; never delete prior Human Brief or delivery revisions.

## Open Questions

None for this issue. Coordinator integration beyond the delivery/acceptance boundary remains assigned to downstream Alpha2 issues.
