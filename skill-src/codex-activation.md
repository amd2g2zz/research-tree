## Activation Receipt

<!-- research-tree-activation: codex:RT-ACTIVE-V1-CODEX -->

Do not claim that `research-tree` is active merely because a similarly named
file was opened. This body is the activation authority for this turn.

When the requester sends `$research-tree --activation-probe`, reply with
exactly `research-tree activation: RT-ACTIVE-V1-CODEX` and do no research,
file inspection, or tool call. This is a host-loading diagnostic, not a
research request.

Before the first external search, delegation, or research-delivery claim in a
normal run, when a Python command runner and writable workspace are available,
record a package-only activation receipt with:

```text
python "<skill-dir>/scripts/activation_receipt.py" --host codex --workspace "<task-workspace>"
```

Resolve `<skill-dir>` from the activated Skill location, not from the task
workspace. The bundled `scripts/activation_receipt.py` contains only package
identity and digest. If the runner or workspace is unavailable, do not
fabricate a receipt; continue with the host-visible activation marker and
record the limitation in debug output.
