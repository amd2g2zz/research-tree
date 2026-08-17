## Design

### Frozen case

`host-conformance-v1`: decision slot with two independent landscape leaves
(A, B), a contradiction phase where A and B submit conflicting claims on one
anchor, a validation phase gated on both leaves, expected canonical event
sequence per host (attempt_started ×2 → worker_finished/unknown per leaf →
contradiction detection → replan retry → validation), and negative oracles
(projected worker_id, synthetic Finding Pack, capability string each fail).

### Harness shape

`evaluation/harness/host_conformance.py` (library): case loader with schema
validation, per-mode runners (codex app-server spawnAgent replay; hermes
synchronous delegation channel in Docker; claude agent/workflow/hybrid per
the #243 contracts), canonical-semantics comparator (kind/sequence/attempt
identity equivalence classes), fault injector (kill/cancel/stale/modified
artifact), replay comparator. `run_host_conformance.py` (CLI): --mode,
--case, --run-root, --fault, writes redacted result JSON per
`host-conformance-result-v1.schema.json`.

### Mode evidence

- codex: #241 receipt methodology (single-process app-server, experimentalApi,
  thread/start + turn/start spawnAgent, subAgentActivity identities).
- hermes: #242 methodology (Docker envelope, pinned image digest, deps
  installed before start, synchronous delegation channel, hook stream).
- claude: #243 contracts (agent/workflow/hybrid selection via
  host_capabilities; real host invocation per its accepted receipts; modes
  that cannot run here record blockers with the precise missing primitive).

### Output

Redacted per-run results under the ignored run root; a tracked comparison
table (`evaluation/results/host-conformance-v1/`) mapping each prior
synthetic/pilot attempt → non-acceptance reason → superseding receipt path.
