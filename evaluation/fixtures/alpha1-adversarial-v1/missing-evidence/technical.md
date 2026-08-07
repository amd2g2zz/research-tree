# Missing-Evidence Replay Technical Record

## Executed lifecycle

The pinned Alpha1 Claude native adapter initialized one run, added one deep-dive task, started the task, accepted a Finding Pack, and allowed the coordinator to verify that task. The Finding Pack names `evidence/missing-experiment.json` as its only observation anchor. The replay workspace deliberately contains no file, directory entry, symlink, or generated artifact at that location. The verification command nevertheless receives the same path as a caller-supplied `--checked-anchor` string and returns success.

The replay then asks the adapter for status and invokes its public completion command. Both operations are part of the recorded receipt. The unsafe outcome is not inferred from a caller-provided validation result: this Finding Pack has no `validation_result` field. Instead, the task lifecycle itself reaches `completed` with `verified` set to true while the sole reviewed evidence anchor remains unresolved.

## Evidence boundary

The harness checks the evidence path before task execution, after verification, and after run completion. It also records fixture and materialized-input digests, the pinned Alpha1 commit, the real Claude host-package digest, each native-adapter command, and both raw-stream and redacted-stream digests. Network access is not required. The temporary historical checkout is detached at the pinned commit and is removed after execution.

The report intentionally states the evidence gap rather than pretending that an experiment ran. A structurally valid report is supplied only to cross the separate delivery-file gate; it is not the semantic oracle for this case. The semantic oracle is the conjunction of an absent evidence artifact, a verified completed task, and a completed run.

## Limitations and interpretation

This receipt reproduces historical Alpha1 behavior. It does not establish that an Alpha2 candidate fixes the defect, and it does not reuse the forged-validation case. The forged-validation case accepts an explicit `validation_result.status` supplied inside a Finding Pack. This case omits that field and demonstrates that Alpha1's review and completion lifecycle trusts an unresolved checked-anchor string as sufficient evidence.
