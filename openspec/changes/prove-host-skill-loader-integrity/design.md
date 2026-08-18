## Design

The shared activation module defines one loader receipt for all supported
hosts. Each receipt binds host/session identity to package and UTF-8
`SKILL.md` byte and line counts, package digest, skill digest, and bounded
loader evidence. Codex and Claude lifecycle observers and the Hermes package
hook record the same redacted shape; host-specific probes may advance the
state from `package_attested` to `host_message_verified` or `live_verified`.

Host adapters continue to report static package checks separately from
`loader_integrity`. A receipt is verified only when all values match the
supplied skill directory and session identity. Missing evidence is
`unverified_loader_integrity`; invalid or stale evidence is rejected.

Host probes are test-only harnesses. The Hermes probe copies a fixture skill
into a fresh `HERMES_HOME`, invokes the supported preload builder, and
compares the emitted skill body to exact on-disk content. Codex and Claude
probes use their native typed/slash activation paths when installed. Start,
middle, and tail mutations demonstrate that a mismatch is detected.

## Failure Handling

- Missing, unreadable, non-UTF-8, or mismatched skill content yields no valid
  receipt.
- A session with no matching receipt remains loader-integrity unverified.
- Observability failures remain non-blocking for Hermes itself, but no test or
  release evidence may call the activation verified.
