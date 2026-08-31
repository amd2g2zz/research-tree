# Tasks: label-agent-facing-output

## 1. Origins vocabulary (RED first)

- [ ] 1.1 RED: `tests/test_origins.py` — `ORIGIN_TYPES` contains exactly
  {user, agent, worker, tool, repository, generated}; `require_origin`
  rejects unknown values with the field name in the message; tag helpers
  always produce well-formed open/close pairs and escape attribute values.
- [ ] 1.2 GREEN: `src/research_tree/origins.py` with `ORIGIN_TYPES`,
  `OriginError(ValueError)`, `require_origin(value, label)`, tag constants
  and `open_tag`/`close_tag` helpers.

## 2. CLI emission labels

- [ ] 2.1 RED: `tests/test_cli_labeled_output.py` — stdout for every verb is
  a balanced `<rt:tool-output ...>` ... `</rt:tool-output>` pair whose inner
  content parses as JSON; failure paths emit `<rt:error ...>` with
  `exit-code`/`category`/`retryability` attributes and the inner envelope
  carries `schema_version` + `contract`.
- [ ] 2.2 GREEN: `cli.py:_emit` wraps payloads; `cli.py:_failure` wraps and
  adds `schema_version`/`contract` to the envelope.

## 3. Lifecycle hook label

- [ ] 3.1 RED: `tests/test_lifecycle_hook_labeled.py` — `host_response`
  output is a balanced `<rt:event contract="research-tree-hook"
  schema_version=... host=...>` pair.
- [ ] 3.2 GREEN: `lifecycle_hook.py` main() wraps the printed host response.

## 4. Observation + actor origin constraints

- [ ] 4.1 RED: `tests/test_host_events_origin.py` — observation payload
  without `origin` rejected; `origin` value outside `ORIGIN_TYPES`
  rejected; `HostEvent.actor` outside `ORIGIN_TYPES` rejected.
- [ ] 4.2 GREEN: `host_events.py` — extend
  `_REQUIRED_PAYLOAD_FIELDS["observation"]` to `("origin",)`; validate
  `origin` membership; constrain `actor` to `ORIGIN_TYPES`.
- [ ] 4.3 Update coordinator-side emitters that construct observation
  events / set actor to write the constrained vocabulary.

## 5. Digest + packet provenance

- [ ] 5.1 RED: `tests/test_insights_produced_by.py` — digest statements
  without `produced_by` rejected; with valid origin accepted.
- [ ] 5.2 GREEN: `insights.py` statements gain `produced_by`; validation
  enforces it.
- [ ] 5.3 RED: `tests/test_contradiction_packet_provenance.py` — rendered
  packet contains an `Origin:` line per claim and a provenance section.
- [ ] 5.4 GREEN: `contradictions.py:render_contradiction_packet` renders
  provenance.

## 6. Shared vocabulary adoption

- [ ] 6.1 `intake.py:ORIGIN_TYPES` imports from `origins.py` (workspace/url
  fold into repository/user per proposal; update callers + tests).
- [ ] 6.2 `alignment_graph.py` node origin field adopts shared vocabulary;
  alignment-specific `source` extensions (joint/reconnaissance/experiment)
  remain on the method `source` field, separate from origin.

## 7. Gate

- [ ] 7.1 Full pytest suite green (no regressions vs 1158+ baseline).
- [ ] 7.2 `uv run --frozen ruff check .` + `ruff format --check .` clean.
- [ ] 7.3 `uv run --frozen python scripts/check_openspec_governance.py`
  valid, zero violations.
- [ ] 7.4 `uv run --frozen python scripts/check_delivery_workflow.py
  validate` passes.
- [ ] 7.5 SKILL docs / host adapters document the `<rt:*>` tag contract for
  machine consumers.
