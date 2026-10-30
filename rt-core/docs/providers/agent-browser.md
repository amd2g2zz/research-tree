# agent-browser — usage guide (rendered-web provider)

Browser-rendered page fetch over the agent-browser CLI (Rust + Chrome CDP; version-pinned by `rt setup`). Headless in CI/unattended runs.

## Fetch

`fetch({ url })` → document `{ url, contentType: "text/markdown", text, bytes }`.

- Pipeline: `read <url>` (agent-readable text); empty read → `open <url>` + accessibility `snapshot` (interaction-gated pages).
- Login state: per-run browser profile config injected via provider config — never the ledger.
- Failure: any non-zero step or read+snapshot-both-empty → structured failure (never silent empty evidence).

Search not supported by contract: search routes to anysearch.
