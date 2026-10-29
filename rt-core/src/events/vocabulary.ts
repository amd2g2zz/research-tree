/** Graph event vocabulary (issue #546, rt-core TS) — public barrel.

Constants live beside the table-driven schemas (./schema.js); this module is
the stable import surface for consumers.

Events are **state-carrying upserts** (plus additive edge facts): replay is
idempotent and rebuild-equality reduces to snapshot comparison.

verify_tier tokens map to docs/product/01-core-algorithms.md A2:
`rederive`=重推导, `multi-source`=多源交叉, `verbatim`=原文摘录,
`single-source`=单源未验, `experiment`=experiment.
*/

export {
  CLAIM_SOURCES,
  EVENT_SPECS,
  GRAPH_EVENT_TYPES,
  GENESIS_HASH,
  VERDICTS,
  VERIFY_TIERS,
  GraphEventError,
  validateGraphEvent,
} from "./schema.js";

export type { EventSpec, FieldSpec, GraphEventType } from "./schema.js";
