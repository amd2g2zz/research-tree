# Proposal: canonical-claim-speech-act-authority

## Why

issue #316: claims.py stored status fields but did not enforce a canonical transition table. Hosts could assert 'accepted' or 'rejected' without authority or basis — making the claim ledger noisy and unreviewable.

## What Changes

NEW `src/research_tree/speech_acts.py`:
- `SpeechAct` frozen dataclass: kind (assert/cite/correction/withdraw), authority_scope, basis_refs.
- `BELIEF_STATUSES = (candidate, supported, refuted, ...)` — 8 canonical states.
- `transition(current, act) -> str`: raises `AuthorityTransitionError` on invalid transition; assert+candidate short-circuit returns current.
- `LEGACY_BELIEF_STATUSES` + `STATUS_LEGACY_MAP` for backward compat.
UPDATE `src/research_tree/claims.py`:
- Add 3 fields: `speech_act: SpeechAct | None`, `claim_kind: str`, `authority: str`.
- Backward-compat defaults; existing tests preserved.

## Impact

src/research_tree/speech_acts.py (new) + src/research_tree/claims.py (extend). Behavior change: claim acceptance now requires valid transition + basis_refs.

## Acceptance ↔ test
| Acceptance | Test |
|---|---|
| assert + candidate + basis_refs short-circuits | test_assertion_with_basis_becomes_candidate |
| unknown belief status raises | test_unknown_belief_status_raises |
| legacy disputed maps to contested | test_legacy_disputed_maps_to_contested |
| claims.py SpeechAct import is graceful | test_claims_speech_act_import_is_graceful |
| transition without basis returns unasserted | test_transition_without_basis_returns_unasserted |
