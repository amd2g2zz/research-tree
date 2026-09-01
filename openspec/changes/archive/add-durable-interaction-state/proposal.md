## Why

The #245 reducer is storage-neutral, so interaction state can be lost across compaction and restart.

## What Changes

- Persist a revisioned YAML-compatible project interaction projection with durable records, episodes, checkpoints, and recall.
- Consume lifecycle observations without changing reducer semantics or host dispatch.

## Non-Goals

- No changes to #245 reduction, evidence adjudication, or host dispatch.
- No raw prompts, transcripts, secrets, or hidden reasoning.
