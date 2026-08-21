## Decision

The raw output committed by the original group-60 verification is unchanged
and has SHA-256
`95b2f6d549404fe51abf52a5a55d131d9acf608c385bfc6c847caa785a7201a8`.
The stale `6ee0…` value is corrected in both the receipt file and the active
verification registry so the test continues to compare one canonical value.

The receipt keeps source revision
`fdb74043df4fa0f0bd31c8023d83f991550bb775`, because this PR repairs metadata
for that historical run rather than presenting a new run from the current
branch as evidence for the old implementation.

## Rollback

Revert the two digest-field changes together. Do not remove the assertion or
replace the historical output with a newly generated local log.
