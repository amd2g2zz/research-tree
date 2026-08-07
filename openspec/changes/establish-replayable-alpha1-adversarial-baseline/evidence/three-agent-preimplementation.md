# #55 three-agent pre-implementation evidence

The prior remote #55 candidate was rejected as a completion artefact: all nine
listed cases were `unavailable`, no input or command replayed Alpha1, and its
classifier accepted caller-provided unsafe booleans / arbitrary evidence strings.

- Operational maintainer: ran the pinned Alpha1 ordinary suite (227 passed) and
  the candidate's fixture tests (9 passed), proving neither result replayed a
  host failure. The report distinguishes this evidence gap from a fix.
- Evaluation auditor: independently clean-cloned the candidate and found 9/9
  unavailable cases, no commands/inputs, semantic leakage through descriptive
  identifiers, and no trustworthy fix-confirmation evidence.
- Root-cause/TDD owner: inspected the pinned tag and found that its Hermes
  adapter accepts technical/human reports purely by byte and heading thresholds;
  Alpha1's own test uses heading-plus-padding reports and receives `complete`.

The first production-quality regression is therefore a real replay of that
filler-report behavior. Other named defects remain pending until their semantic
replay predicates are demonstrated.

## Agent 1 post-implementation gaps to carry forward

The independent black-box review reports that the prior submitted HEAD covered
only 1 of 9 named issue defects. After the forged-validation slice in this
worktree, the executable count is 2 of 9; missing evidence, empty frontier,
active contradiction, repeated reconnaissance, adapter-only completion,
provider failure, and crash recovery remain pending.

The review also identifies three receipt/contract gaps that this slice does not
silently claim to solve:

1. The corpus still needs one governed nine-defect manifest. A pair of executable
   receipts is not a complete issue inventory.
2. Existing filler-report receipts label `stdout_sha256` as the digest of the raw
   stream while retaining only redacted stdout. That is not independently
   reproducible from the committed artifact. Future receipt work must either
   retain a governed raw stream reference or explicitly distinguish raw and
   redacted digests. The new forged-validation receipt records both namespaced
   digest forms; the legacy filler receipt remains pending migration.
3. The replay CLI help says the execution workspace is removed, while the
   implementation removes only the generated workspace subdirectory and the
   detached checkout, leaving the caller-owned empty `work_root`. Help text and
   cleanup semantics need to be reconciled without changing disposable-root
   safety.

These are recorded as follow-up acceptance gaps, not converted into green
claims for the forged-validation oracle.
