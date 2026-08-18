The test matrix copies each generated host package, creates a session-bound
receipt, mutates or truncates the first, middle, and tail of `SKILL.md`, and
asserts `invalid_loader_receipt`. It separately varies session identity and
the activation gate's loader, alignment, and handoff states. Every invalid
case must remain blocked and no test writes a research artifact.
