# Design

`AdaptiveResearchPolicy` is a pure, deterministic reader of normalized Slot
deficits, verified evidence, Insight signals, prior outcomes, configuration,
and a seed. It returns typed proposals, dispositions, and an audit trace. It
does not persist, dispatch, acquire sources, manage leases, or mutate lifecycle
state; `ResearchRunCoordinator` remains the sole authority.

The six-component immutable delta compares evidence-class coverage, provenance
independence, contradiction, oracle state, implementation uncertainty, and Slot
closure. Each component carries references and contribution. Repeated or
historical input returns zero delta and a no-progress penalty.

Ranking is versioned and replayable: canonical normalized input, configuration,
policy version, and seed determine score order and tie-breaks. P0 validation,
counterevidence, contradiction, and required obligations survive optional
capacity pruning. Unverified worker suggestions are rejected.

Insight Digest synthesis validates exact Finding Pack and Slot lineage, emits
classified facts/hypotheses, gaps, contradictions, limitations, confidence,
parent/digest references, and the delta. It is an input projection only and
cannot issue closure or completion.

Legacy recursive search remains a read-only compatibility projection. Empty
frontiers, worker returns, task counts, reports, byte/heading gates, and local
delivery checks produce observations or blockers; they cannot close a Slot,
accept delivery, or complete a run.

Rollback disables policy selection while retaining historical evidence and
digests. It must not restore a writable legacy completion path. #59 alignment,
#60 host events, #73 invalidation, #80 capture, and #83 portfolio acquisition
remain outside this change.
