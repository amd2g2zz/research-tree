## Context

Group 8 established a strict HostEvent envelope and coordinator-only ingestion for Codex and Claude. Hermes still writes `.research-tree-hermes/state.json`, treats batches as lifecycle state, and completes runs from local report shape. Provider interruption can therefore leave Hermes and the canonical ledger disagreeing.

## Goals / Non-Goals

**Goals:**

- Translate Hermes delegation/provider observations into the existing HostEvent contract.
- Recover running work from canonical attempts, recording unknown outcome before retry.
- Sanitize provider diagnostics and project canonical actions into Hermes goals/Kanban.
- Remove local completion/report authority while retaining compatible observation commands.

**Non-Goals:**

- New tracing, activation, capture/checkpoint, workflow, scheduler, lease, or method-registry authority.
- Raw provider-log ingestion or changes to Codex/Claude event semantics.

## Decisions

1. **Use a stateless Hermes translator.** Event ids, payload digests, sequences, and attempt lineage derive from explicit inputs and canonical state. A new Hermes-specific state store was rejected because it recreates split authority.
2. **Recover through coordinator queries and HostEvents.** Restart reads canonical active attempts; unresolved work emits `unknown_outcome`, then a separately authorized retry event/new attempt. Inferring success from child exit or an empty queue was rejected because neither carries evidence or closure authority.
3. **Treat goals and Kanban as projections.** Records contain canonical action/attempt ids and acceptance criteria and can be rebuilt. Writing lifecycle state back from a card was rejected because host UI state is lossy.
4. **Whitelist provider metadata.** Store normalized provider/model identifiers, retry category, opaque error code, and normalized workspace-relative log reference. Raw messages, prompts, tokens, absolute paths, and unbounded fields are rejected rather than redacted heuristically.
5. **Keep hooks fail-open and observational.** Hooks may emit sanitized wake-up metadata, but canonical ingestion requires the normal validated adapter path. Treating hooks as enforcement was rejected because Hermes hook failures are explicitly non-blocking.
6. **Preserve bounded compatibility commands.** Existing init/batch/recover/complete entry points may return observation/projection summaries during migration, but must not write `.research-tree-hermes/state.json`, verify Markdown structure, or return canonical completion.

## Risks / Trade-offs

- **[Risk] Host sequence races after restart** -> Require exact expected revision/sequence and idempotent event replay; conflicts are visible, never overwritten.
- **[Risk] Sanitization drops useful diagnostics** -> Keep an opaque error code and safe log reference while leaving raw logs outside canonical evidence.
- **[Risk] Legacy callers expect local complete** -> Return explicit `completion_authority=coordinator_only` and `observed_complete` compatibility fields, then remove them in a later migration.
- **[Risk] Method switch expands #83 scope** -> Accept only a coordinator-issued action/method identifier already inside the confirmed authority envelope.

## Migration Plan

1. Add failing translator, sanitization, recovery, authority-bypass, and package parity tests.
2. Implement shared Hermes event/projection helpers and coordinator recovery composition.
3. Replace local checkpoint/report behavior and rebuild generated Hermes packages in an isolated commit.
4. Record the group 9 receipt and retain legacy checkpoint files as read-only user data; never delete them automatically.

Rollback disables the translator/projection and leaves accepted HostEvents readable. It cannot re-enable local completion or report gates.

## Open Questions

No blocking design questions remain. Live Hermes activation evidence belongs to #71; this change records only testable static/runtime behavior.
