# ADR-007: Pydantic annotation boundary for new modules

- Status: accepted (2026-08-30)
- Deciders: maintainer (user ruling, alpha3 batch 1 planning session)
- Supersedes: none; amends ADR-001 (stdlib-only production code)

## Context

ADR-001 froze runtime dependencies at zero and the codebase hand-rolls
`Mapping[str, Any]` whitelist validation (~420 call sites).  The maintainer
ruled on 2026-08-29 that new code must carry enforced (pydantic) annotations.

## Decision

1. Pydantic enters as a **test/dev group dependency first**; promoting it to
   runtime `dependencies` requires an explicit maintainer decision recorded
   here.
2. New modules added from alpha3 batch 1 onward define payload schemas in
   `src/research_tree/schemas.py` with `extra="forbid"` (matching legacy
   whitelist semantics: error messages must name the offending field).
3. Existing modules are **not** backfilled.  Backfill order is decided per
   batch by pilot evidence (Phase 4 of the alpha3 batch 1 plan).
4. Ruff legacy exemptions (PLR2004/ARG/SIM/B families, loose PLR thresholds)
   recorded in `pyproject.toml` are consumed by this same boundary: new files
   carry zero exemptions, touched files clear theirs opportunistically.

## Alternatives considered

- Full pydantic migration of all modules: rejected — couples 4 issue PRs to a
  420-site rewrite; sequencing belongs to pilot-informed batches.
- TypedDict-only annotations: rejected — runtime-unenforced, does not satisfy
  the "forced" requirement.

## Consequences

- Dual validation styles coexist until backfill completes; schemas.py is the
  single entry point for the new style.
- uv.lock now carries pydantic in non-runtime groups; packaging stays stdlib.
