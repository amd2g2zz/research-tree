## Why

Content-addressed captures prove that bytes were preserved, not that a worker's
normalized statement is true. Search provider and method diversity also does
not prove that evidence came from separate upstream origins. Consequently, a
single high-confidence worker result can currently stop an acquisition batch.

## What Changes

- Define atomic consequential claims, source-grounding records, provenance
  clusters, and fail-closed admission states.
- Derive corroboration from independently resolved provenance clusters rather
  than worker confidence, provider count, method count, or URL count.
- Prevent an acquisition batch with material isolated, rejected, or superseded
  claims from producing a `stop` disposition.
- Preserve non-admitted claims as auditable leads without decision authority.

## Non-goals

- This change does not resolve conflicts among admitted claims; #248 owns
  contradiction detection and contested-state propagation.
- This change does not persist interaction state or alter host dispatch.
