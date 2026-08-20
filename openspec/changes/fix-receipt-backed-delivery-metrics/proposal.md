## Why

Delivery reports previously passed a shallow file-shape check, allowing prose to
report a different outcome from retained runtime evidence.

## What Changes

- Derive one version-bound delivery receipt snapshot from host execution state.
- Render both delivery reports deterministically from that snapshot.
- Reject reports whose metrics, receipt digest, or prose do not match the
  canonical projection.

## Scope

This change governs host-local delivery observations. It does not promote a
host observation to canonical coordinator completion.
