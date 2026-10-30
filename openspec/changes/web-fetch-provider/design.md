# design — web-fetch-provider

Content-type routing: text/html → readability path; text/plain & code → raw
+ summary; pdf/office (content-type + extension sniffing) → download to a
temp file → markitdown (positional file argument, the real CLI shape) →
markdown. Deterministic summary: block-leading lines as the outline (plain
text), fenced-block inventory with language tags (markdown-ish), naive
extension/language detection (code) — all mechanical, zero model calls.

## impact_scope

As in proposal.md. No existing callers (port consumers register the adapter
in the composition wave).

## rejected_designs

- Self-implementing office converters (markitdown is MIT, battle-tested — the
  ruling says reuse when it exists).
- LLM-based summaries in the provider layer (understanding is downstream; the
  provider layer stays mechanical).
- Trusting URL extensions over content-type sniffing (both used, sniffing wins
  conflicts).
- Unbounded downloads (cap + timeout; oversize = structured failure).
