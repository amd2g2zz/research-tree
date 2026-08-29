# Documentation Authority

Start at the [Documentation hub](../README.md). It routes requesters, AI agents,
operators, contributors, and evaluators to the smallest relevant set of active
documents.

The machine-readable authority index is
[`documentation-authority-v1.json`](../../openspec/changes/unify-research-runtime-alpha2/registries/documentation-authority-v1.json).
It is the canonical inventory for each governed document root: its authority,
owner, audience, lifecycle, canonical edit location, update trigger,
supersession rule, and validation rule.

Use the registry precedence when documents conflict. `PRODUCT.md` governs
current product behavior; ADRs govern accepted architecture; an active OpenSpec
change governs its pending implementation contract. `docs/specs/` and
`docs/reviews/` are historical records and cannot override an active contract.

The consolidated `需求理解.md` and `方案设计.md` files are historical and live in `docs/history/`.
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

## Release claim tiers

Release governance distinguishes four claim tiers. An open issue constrains
specific claims; it never silently blocks the existence of the published tag.

| Tier | Claim | Governed by |
|---|---|---|
| `published` | The package exists, installs, and passes its own quality gates on a clean checkout. | `master` branch protection; tag provenance. |
| `alpha-pilot-suitable` | Usable for supervised Alpha pilots with known evidence debt. | Open issues that declare this tier. |
| `org-rollout-ready` | Fit for organization-wide adoption without per-team supervision. | Independent-implementation and adoption evidence (#292). |
| `unattended-final-authority` | Trusted as the final authority for unsupervised long-horizon research. | Closed black-box evaluation with zero false completions (#84, #323). |

Per-issue gate declarations (what each open evaluation issue gates and what it
does not):

- #67 gates alpha-pilot-suitable evidence-debt accounting; does not gate published.
  Alpha2 was published under the rolling-Alpha policy while #67 stayed open;
  the open items are recorded evidence debt and limits on stronger claims, not
  blockers on the tag. A released Alpha with known debt carries explicit
  limitations, rollback triggers, and follow-up metrics — it is never reported
  as falsely complete.
- #84 gates unattended-final-authority, org-rollout-ready; does not gate
  published, alpha-pilot-suitable. An open paired benchmark limits the strength
  of comparative claims; it cannot become an infinite code-release blocker.
- #292 gates org-rollout-ready; does not gate published, alpha-pilot-suitable.
  Senior-user adoption evidence shapes rollout claims only.
- #323 gates unattended-final-authority; does not gate published,
  alpha-pilot-suitable, org-rollout-ready. Black-box regression evaluation for
  cognition, growth, and disagreement is final-authority evidence.

Branch discipline is unchanged and orthogonal to tiers: `master` remains the
protected published branch, `dev` integration and release promotion remain
PR-governed. Closing an implementation issue on `dev` and shipping it on
`master` are distinct states; once a fix is reachable from the released tag it
is not reported as unreleased.
