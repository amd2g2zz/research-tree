## Context

The interaction controller must remain active throughout a research project,
but #245 cannot introduce a second durable runtime or completion authority.

## Decisions

1. `InteractionReducer.reduce(prior, event)` is deterministic and
   storage-neutral.  Persistence and hook delivery are later consumers of the
   same state/event contract.
2. Authority is monotonic only from explicit requester event authority.  It is
   never inferred from reconnaissance, acknowledgement, silence, or `continue`.
3. A correction records an exact superseded identity, removes agent
   assumptions, invalidates only transitively dependent unexecuted pending
   actions, retains unrelated work, raises error debt, and returns `repair`.
4. Alignment exposes a narrow bridge only; it does not transition lifecycle,
   grant authority, or declare delivery complete.

## Risks

- A reducer can over-ask questions.  Only a high-consequence, non-reversible
  request enters `request_decision`; clear reversible work executes directly.
- State can be lost before #246 persistence.  The contract is explicit and
  serializable through frozen value objects, and later persistence does not
  need to reinterpret dialogue.
