## Why

Copy installations could be byte-identical yet look indistinguishable from an
unsupported user-owned directory, while doctor output omitted the reason and
the compared content identity.

## What Changes

- Report a copied installation as `current` only when package digests match.
- Preserve path-aware link diagnostics without reading a foreign link target.
- Distinguish missing targets, conflicts, legacy payloads, missing referenced
  resources, and digest mismatches with deterministic reasons.
