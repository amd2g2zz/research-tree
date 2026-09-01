## Why

The released host adapter can convert an unvalidated Finding Pack and a
caller-supplied reviewer label into `completed` task state. That state is not a
canonical lifecycle decision and does not prove independent review.

## What Changes

- Keep adapter task state at `submitted` after a review observation; reserve
  canonical completion for `ResearchRunCoordinator`.
- Require a passed validation result before a review observation can be
  recorded.
- Bind both worker and reviewer identities to observed host records, and
  require distinct principal, session, lease, and evidence-custody references.
- Preserve worker bindings through submission and keep host status explicitly
  observational.
- Make the Hermes bridge report no inferred completion without canonical
  evidence, and regenerate every host package.

## Impact

- Changes the native adapter review CLI contract and durable projection shape.
- Preserves dependency waves through independently reviewed submissions.
- Does not change the canonical completion manifold or human acceptance gate.
