## Context

The Alpha2 runtime already provides a digest-verified workspace CAS and an
expected-revision SQLite ledger. Source acquisition and worker events currently
use free-form payloads, leaving crash recovery and privacy boundaries implicit.

## Goals / Non-Goals

**Goals:**

- Publish immutable capture, receipt, and checkpoint payloads through the ledger.
- Verify CAS bytes before committing a successful receipt.
- Make checkpoint references same-run and resumable, with typed quarantine for
  incomplete attempts.
- Keep checkpoints bounded and reject sensitive prompt/secret/private-reasoning
  fields.

**Non-Goals:**

- Provider-specific fetching, host-owned stores, private chain-of-thought, or
  replacing EvidenceArtifact.

## Decisions

1. Use frozen dataclasses with canonical `to_dict`/`from_dict` validation. This
   keeps schemas host-independent and lets ledger artifact hashes provide
   immutability.
2. Persist captures as `source-capture`, receipts as `acquisition-receipt`, and
   checkpoints as `analysis-checkpoint` artifacts. Content is committed with
   `append_artifact_with_content`; receipt success is impossible without CAS
   verification.
3. Keep capture provenance on every acquisition (including duplicate CAS bytes)
   and use an explicit `origin_capture_id` for derivatives.
4. Expose `validate_worker_finished` as a pure gate. It checks run/attempt
   identity, committed statuses, and checkpoint refs before host completion is
   accepted; malformed or partial attempts return `capture_incomplete` data for
   quarantine and next action.

## Risks / Trade-offs

- [A crashed process can leave staged CAS bytes] -> existing orphan quarantine
  remains authoritative; unbound bytes are never returned as captures.
- [Strict redaction can reject legitimate prose] -> reject only key names and
  obvious secret patterns, with a typed validation error for caller handling.
- [A checkpoint can grow without bound] -> enforce item and serialized-byte
  limits before ledger append.

## Migration Plan

New artifacts are additive. Existing runs remain readable. Rollback can disable
the worker-finished gate while retaining capture/checkpoint artifacts as
read-only history.
