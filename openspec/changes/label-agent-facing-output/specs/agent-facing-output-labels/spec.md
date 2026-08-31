## ADDED Requirements

### Requirement: Agent-facing output carries balanced origin labels

Every research-tree output that enters an agent's context SHALL be wrapped
in a balanced open/close XML tag identifying its source, so a consuming
agent (including a compacted self or a handoff subagent) can mechanically
separate external tool output from its own generated content. Tag pairs
SHALL be well-formed: an unclosed or truncated tagged block is a consumer
error, not content. Payload inside tags SHALL be raw — research-tree SHALL
NOT interleave its own interpretation inside tags; summaries and judgments
stay outside the tags.

#### Scenario: CLI success output is labeled

- **WHEN** the CLI emits a successful command payload
- **THEN** stdout is exactly one balanced
  `<rt:tool-output source="research-tree-cli" command="..." run="..." rev="...">`
  ... `</rt:tool-output>` pair whose inner content parses as JSON

#### Scenario: CLI failure output is labeled and versioned

- **WHEN** a command fails and the CLI emits the failure envelope
- **THEN** stdout is a balanced `<rt:error source="research-tree-cli"
  exit-code="..." category="..." retryability="...">` ... `</rt:error>`
  pair, and the inner envelope carries `schema_version` and `contract`
  fields with the same discipline as success payloads

#### Scenario: Hook host response is labeled

- **WHEN** the lifecycle hook prints its non-blocking host response
- **THEN** stdout is a balanced
  `<rt:event contract="research-tree-hook" schema_version="..." host="...">`
  ... `</rt:event>` pair

### Requirement: Observations carry a required origin

An observation host event SHALL carry an `origin` key in its payload drawn
from the closed `ORIGIN_TYPES` vocabulary
(`user | agent | worker | tool | repository | generated`). An observation
without `origin`, or with an origin outside the vocabulary, SHALL be
rejected at the HostEvent envelope validation, fail-closed, with an error
naming the field.

#### Scenario: Observation without origin is rejected

- **WHEN** a caller submits an observation host event whose payload lacks
  `origin`
- **THEN** the HostEvent envelope validation raises, naming the missing
  `origin` field

#### Scenario: Retellings are distinguishable from verified observations

- **WHEN** a worker reports an observation and the agent records its own
  verified observation
- **THEN** the two ledger entries carry different `origin` values
  (`worker` vs `agent`), and downstream consumers (understanding debt,
  state projection) can discount retellings accordingly

### Requirement: HostEvent actor is a closed vocabulary

`HostEvent.actor` SHALL be drawn from `ORIGIN_TYPES`. An actor value
outside the vocabulary SHALL be rejected at envelope validation. The
programmatic emitters inside the coordinator default to `agent`.

#### Scenario: Free-form actor rejected

- **WHEN** a caller constructs a HostEvent with `actor="some-random-string"`
- **THEN** envelope validation raises with an error naming the allowed
  vocabulary

### Requirement: One origin vocabulary across layers

intake `origin.type`, HostEvent `origin`/`actor`, insight statement
`produced_by`, and the alignment node origin field SHALL all draw from the
single `ORIGIN_TYPES` set defined in `src/research_tree/origins.py`. No
module SHALL define a private divergent origin vocabulary. Alignment keeps
its method-level `source` extensions (joint/reconnaissance/experiment) on
the separate method `source` field, which describes how the node was
produced, not who spoke.

#### Scenario: Digest statements name their producer

- **WHEN** the insights digest is synthesized
- **THEN** every statement carries `produced_by` drawn from `ORIGIN_TYPES`,
  and digest validation rejects statements without it

#### Scenario: Rendered contradiction packets keep provenance

- **WHEN** `render_contradiction_packet` renders a packet for agent
  consumption
- **THEN** the rendering includes a provenance section with one `Origin:`
  line per claim
