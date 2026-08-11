## ADDED Requirements

### Requirement: deterministic evidence-bound proposals

The policy SHALL accept normalized Slot deficits, verified evidence, digest
signals, prior outcomes, versioned configuration, and a seed. It SHALL return
only `landscape`, `deep_dive`, `adversarial`, `validation`, or `method_switch`
proposals, explicit deferrals, or rejections. Each retained proposal names its
Slot, trigger, missing dimension, method boundary, closure oracle, score, and
causal references. Worker-only suggestions without verified triggers SHALL be
rejected.

### Requirement: replayable ranking and pruning

Selection SHALL be derived from policy version, canonical input, configuration,
and seed, with score components, normalization, tie-break, and reasons in the
trace. P0 validation, counterevidence, contradiction, and required obligations
remain eligible when optional frontier capacity is exhausted. Equal inputs SHALL
produce equal identifiers, order, scores, and dispositions.

### Requirement: six-component attributable delta

The immutable comparison SHALL cover evidence-class coverage, provenance
independence, contradiction, oracle state, implementation uncertainty, and Slot
closure. Each component SHALL expose references and contribution. Repeated or
historical state SHALL produce zero delta and a no-progress penalty.

### Requirement: compatibility has no lifecycle authority

Recursive compatibility APIs SHALL return observations, blockers, or proposals.
Worker returns, empty frontiers, task counts, report presence, byte/heading
gates, and local delivery checks SHALL NOT close Slots or complete runs.
