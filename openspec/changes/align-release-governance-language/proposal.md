# Proposal: align-release-governance-language

## Why

issue #331: #67 still says Alpha2 is "releasable only when" #84 and all
release-definition gates close, yet 0.1.0-alpha2 was intentionally published
under the rolling-Alpha policy. The absolutist wording makes agents infer
"open benchmark issue means cannot release," which already produced incorrect
release advice.

## What Changes

`docs/governance/documentation-authority.md` gains a "Release claim tiers"
section: four tiers (`published`, `alpha-pilot-suitable`, `org-rollout-ready`,
`unattended-final-authority`) plus per-issue gate declarations for #67, #84,
#292, #323 (gates X; does not gate Y). New test file locks the vocabulary,
the per-issue declarations, tier-name validity, and the absence of
absolute-blocking phrases in active governance docs. #67 gets a
cross-link comment (GitHub side, done in main session).

## Impact

- docs/governance/documentation-authority.md (+~45 lines)
- tests/test_release_governance_tiers.py (new, 4 tests)
- No policy semantics change; branch discipline unchanged.
