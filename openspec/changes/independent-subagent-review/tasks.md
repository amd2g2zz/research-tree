# Tasks

## 1. Artifact contracts

- [ ] 1.1 Add `src/research_tree/independent_review.py`: schema-1 payload
      validators for `alignment-verification` and `delivery-review` with
      named-field errors, the fail-closed identity rule, and the shared
      role/kind constants.
- [ ] 1.2 Add `CompletionInputRegistrar.write_alignment_verification` and
      `write_delivery_review`, binding parent lineage to the projection
      revision and to the evidence custody references, and admit the two
      roles in the ledger's completion-input channel.

## 2. Runtime gates

- [ ] 2.1 Display gate: reject `display_strategy` and the
      `alignment_projection_ready` guard with
      `independent_verification_required` unless a current, identity-
      independent verification binds the projection content (authority
      fingerprint) and restates every oracle; pre-flight the gate in the
      CLI display verb so a rejected display appends no artifact.
- [ ] 2.2 Delivery gate: add the `independent_delivery_review` completion
      diagnostic (missing / same-identity / custody lineage / custody
      stale / oracle coverage / unmet verdict), surface
      `resolve:independent_delivery_review[:<oracle_id>]` next actions, and
      record `independent_review_refs` in the completion manifold.
- [ ] 2.3 Keep #441 falsifiability and #443 goal_satisfaction conjunctive:
      both still block on their own reasons with the new artifacts present.

## 3. Behavioral layer

- [ ] 3.1 SKILL.template.md and hermes-SKILL.template.md: display-time
      alignment restatement dispatch and delivery-time per-oracle verdict
      dispatch, with the named rejection codes.
- [ ] 3.2 claude-adapter.md, codex-adapter.md, hermes-adapter.md: one
      host-native subagent dispatch instruction each; self-issued reviews
      are rejected.
- [ ] 3.3 Regenerate host packages as a generated-only commit and keep the
      SKILL line budget and forced-load word budget intact.

## 4. Validation

- [ ] 4.1 Red-green tests in `tests/test_independent_review.py`: named
      display/delivery rejections (missing artifact, same identity,
      missing identity, content mismatch, custody drift, coverage gaps,
      unmet verdict), independent passes, conjunction with #441/#443,
      direct-transition enforcement, and artifact lineage binding.
- [ ] 4.2 Update the shared fixtures (`tests/strategy_support.py`,
      coordinator completion fixtures) to produce the review artifacts.
