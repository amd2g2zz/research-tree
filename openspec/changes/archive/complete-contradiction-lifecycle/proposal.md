## Why

The existing slice detects exact conflicts but lacks typed applicability,
immutable resolution authority, atomic downstream retraction, and exact packet
identifiers in readiness/delivery failures.

## What Changes

- Use one typed detector at every canonical claim boundary.
- Add immutable packet, resolution, retraction, and successor-work artifacts.
- Atomically revoke dependent decisions, deliveries, closure, execution, and durable state.
- Render exact packets and fail closed until fresh lineage follows a terminal resolution.

## Non-Goals

No historical migration, claim-schema rewrite, host-adapter ownership change, or
external automatic truth resolution.
