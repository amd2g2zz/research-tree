The shared `evaluate_activation_gate` function is the narrow policy boundary:
only `host_message_verified` or `live_verified` loader evidence, an alignment
state of `equilibrium`, and an explicit `confirmed` handoff allow a research,
dispatch, or delegation action. Every other state returns `blocked` with a
stable code. The function does not dispatch or persist work.

The common Codex/Claude template and Hermes template carry the same ordered
state machine and positive/negative trigger language. Host-specific invocation
syntax remains in each adapter, while the activation disposition remains
identical. Missing tools, resources, context capacity, or provider access are
explicit blocked/unavailable outcomes and never implicit authorization.
