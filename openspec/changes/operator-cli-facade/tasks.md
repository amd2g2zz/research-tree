## 1. Bind bridge

- [ ] 1.1 Add the optional `alignment_handoff` parent to
      `CanonicalBlueprintTargetCompiler.compile` with fail-closed resolution
      (same run, exact stored revision, `alignment-handoff` kind).
- [ ] 1.2 Unit-prove the bind: parent_refs carry the exact handoff revision;
      foreign/missing handoffs are rejected; the default call compiles
      unchanged.

## 2. CLI init chain

- [ ] 2.1 Add `research-tree initialize` (handoff resolve/compile, optional
      brief document compile, blueprint compile with bind,
      `coordinator.initialize`, optional decision frame persist).
- [ ] 2.2 Extend `strategy propose` with `--alignment-verification` and base
      projection documents (product computes display payload/digest/hash).
- [ ] 2.3 CLI-journey test: run -> initialize -> propose -> display -> confirm
      with named-failure coverage (`working_brief_missing`).

## 3. Operating model exposure

- [ ] 3.1 Add `research-tree operating-model` rendering the canonical
      operating model as markdown.

## 4. Packaged record fix

- [ ] 4.1 Ship `speech_acts.py` beside the packaged alignment controller and
      add sibling-module fallbacks to the two lazy imports.
- [ ] 4.2 Subprocess test asserting the packaged `record` path exits 0.

## 5. Delivery hygiene

- [ ] 5.1 Regenerate host packages; keep the packages/** commit
      generated-only.
- [ ] 5.2 Write `docs/evaluation/research/v2-followup-cli-journey.md` as the
      fresh CLI-only acceptance log.
