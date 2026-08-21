# Documentation Authority

Start at the [Documentation hub](README.md). It routes requesters, AI agents,
operators, contributors, and evaluators to the smallest relevant set of active
documents.

The machine-readable authority index is
[`documentation-authority-v1.json`](../openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json).
It is the canonical inventory for each governed document root: its authority,
owner, audience, lifecycle, canonical edit location, update trigger,
supersession rule, and validation rule.

Use the registry precedence when documents conflict. `PRODUCT.md` governs
current product behavior; ADRs govern accepted architecture; an active OpenSpec
change governs its pending implementation contract. `docs/specs/` and
`docs/reviews/` are historical records and cannot override an active contract.

The consolidated `需求理解.md` and `方案设计.md` files are also historical.
They preserve early delivery context but are not current product, architecture,
or implementation authority.

Edit `skill-src/`, `assets/`, `references/`, or registered scripts as authoring
sources. Never edit `packages/` documentation directly: rebuild it with
`uv run python scripts/build_skill_packages.py` and verify provenance with
`uv run python scripts/build_skill_packages.py --check`.

Operational guidance belongs under `docs/`, evaluation evidence belongs under
`evaluation/`, and user-owned runtime reports/session logs do not belong in
tracked authoring roots. The documentation gate checks these boundaries:

```text
uv run python scripts/check_docs.py
```

Active delivery documentation calls the two outputs the Technical Research
Package and Human Research Report. Historical or generated compatibility
material may preserve previous artifact labels only when the registry records a
compatibility disposition or historical supersession.
