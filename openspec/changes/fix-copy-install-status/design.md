## Design

Status first checks target existence and link identity. A mismatched link is a
`conflict` with `link_target_mismatch`, and its foreign payload is not read.
For a regular directory, the installer validates the skill payload and compares
canonical package digests. `skill_status` includes source and target digest
fields whenever a safe comparison is available.

Installation still refuses to overwrite conflicts. Removing a known bad copy
and reinstalling produces a new digest-current target.
