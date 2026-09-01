# Proposal: label-agent-facing-output

## Why

Agents (main agent, compacted selves, handoff subagents) cannot mechanically
distinguish in their own context which content they generated themselves vs
which content flowed back from research-tree tools, workers, and hosts
(issue #440). Audit of the output surfaces:

- `cli.py:_emit` prints bare `json.dumps(payload)` — no marker identifying
  the line as research-tree tool output.
- `cli.py:_failure` emits a failure envelope without `schema_version` /
  `contract` (the success payloads carry both) — consumers cannot confirm
  the format contract on error paths.
- `lifecycle_hook.py:293` prints `{"continue": true}` with no contract
  marker — a host agent cannot tell this is the research-tree hook contract.
- `host_events.py:37` `_REQUIRED_PAYLOAD_FIELDS["observation"] = ()` —
  observations enter canonical state without a required origin, so a
  worker's retelling and an agent's own verified observation are
  indistinguishable downstream (understanding-debt machinery has nothing to
  key on).
- `insights.py` digest statements carry evidence refs but no `produced_by`.
- `contradictions.py:render_contradiction_packet` renders markdown that
  drops provenance.
- Three divergent origin vocabularies exist: intake `origin.type`
  (user/workspace/url/repository/generated, intake.py:50), alignment
  `source` (human/agent/joint/reconnaissance/repository/experiment,
  alignment_graph.py:82), and HostEvent `actor` (free string,
  host_events.py:95).

Concrete failure: after `/compact` or subagent handoff, a JSON line in the
transcript that the agent itself fabricated as "expected output" is
indistinguishable from a real tool response — hallucinated output and
verified tool output carry equal weight in memory.

## What Changes

Maintainer ruling (user, 2026-09-01): the labeling format is **balanced
open/close XML tags** — the same envelope discipline the harness uses for
`<system-reminder>` / `<task-notification>`, so downstream agents can
re-parse mechanically.

- NEW `src/research_tree/origins.py`:
  - `ORIGIN_TYPES = frozenset({"user", "agent", "worker", "tool", "repository", "generated"})`
  - `require_origin(value, label)` validator (fail-closed, names the field).
  - XML tag constants (`TOOL_OUTPUT`, `OBSERVATION`, `DIGEST`, `EVENT`,
    `ERROR`) with `open_tag(attributes) -> str` / `close_tag` helpers that
    escape attribute values and guarantee well-formed pairs.
- `cli.py:_emit` wraps every emitted payload in
  `<rt:tool-output source="research-tree-cli" command=... run=... rev=...>`
  ... `</rt:tool-output>`. Machine consumers parse the JSON inside the
  tags; humans read it unchanged.
- `cli.py:_failure` emits inside `<rt:error source="research-tree-cli"
  exit-code=... category=... retryability=...>` ... `</rt:error>` and the
  inner envelope gains `schema_version` + `contract` fields (same shape
  discipline as `_stable_payload`).
- `lifecycle_hook.py:293` prints
  `<rt:event contract="research-tree-hook" schema_version=... host=...>`
  ... `</rt:event>` around the host response.
- `host_events.py`: `_REQUIRED_PAYLOAD_FIELDS["observation"]` requires an
  `origin` key drawn from `ORIGIN_TYPES`; `HostEvent.actor` is validated
  against `ORIGIN_TYPES` (fail-closed). Default for programmatic emitters
  is their own component role (`agent` for coordinator-originated events).
- `insights.py`: digest statements gain `produced_by` (an origin label);
  digest validation requires it.
- `contradictions.py:render_contradiction_packet` gains a provenance
  section; each claim renders one `Origin:` line.
- intake `origin.type` and alignment `source` adopt the shared
  `ORIGIN_TYPES` vocabulary. Compat mapping is NOT shipped (alpha3
  zero-compat ruling #422): callers write the new vocabulary directly;
  alignment `joint`/`reconnaissance`/`experiment` are preserved as
  alignment-specific `source` extensions layered on the base origin (they
  describe method, not who spoke — the origin field is separate).

## Impact

- `src/research_tree/origins.py` (new), `cli.py`, `lifecycle_hook.py`,
  `host_events.py`, `insights.py`, `contradictions.py`, `intake.py`,
  `alignment_graph.py` + tests for each.
- Consumers that machine-parse CLI stdout must strip/parse the XML wrapper;
  the stable contract is documented in SKILL docs and the host adapters.
- No stored-history migration: new writes only (alpha3 zero-compat ruling).

## Acceptance ↔ test

| Acceptance | Test |
|---|---|
| CLI stdout always well-formed open/close pair | test_cli_emits_balanced_tool_output_tags |
| Failure output carries rt:error + schema_version + contract | test_failure_envelope_is_labeled_and_versioned |
| Hook host response wrapped in rt:event | test_hook_host_response_labeled |
| Observation without origin rejected | test_observation_requires_origin |
| HostEvent actor outside ORIGIN_TYPES rejected | test_host_event_actor_constrained |
| Insights statements carry produced_by | test_insight_statements_have_produced_by |
| Contradiction packet renders Origin lines | test_contradiction_packet_renders_provenance |
| require_origin fail-closed names the field | test_require_origin_rejects_unknown |
| Unbalanced tag helpers impossible | test_tag_helpers_always_close |
