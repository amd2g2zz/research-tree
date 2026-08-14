# Repair Group-60 Verification Digest

## Why

The historical group-60 receipt declares an output digest that does not match
the immutable raw output file it references. This makes the active verification
test fail even though the recorded command result is otherwise valid.

## Scope

- Correct the group-60 receipt and its canonical verification-registry copy to
  the SHA-256 of the unchanged raw output bytes.
- Keep the historical command, source revision, environment digest, and raw
  output unchanged.
- Preserve the #188 prevention boundary and leave runtime code untouched.

## Non-goals

- Do not rerun the historical command and claim a new source-bound result.
- Do not weaken the digest assertion or delete the group-60 evidence in this
  repair.
- Do not migrate other generated records; #194 owns that bounded migration.
