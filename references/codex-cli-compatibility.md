# Codex CLI Compatibility

Use this reference when `research-tree` runs under Codex CLI. The capability is
session-dependent; a skill must inspect what the current host exposes instead of
calling a tool by name from another host.

## User questions

Codex's app-server protocol defines an experimental `request_user_input`
request. Its payload contains `threadId`, `turnId`, `itemId`, `questions`, and
`isBlocking`; each question can include an `id`, `header`, `question`, and
optional labeled/description options. The client returns an answer map keyed by
question id. The protocol does not make this request available to every CLI
skill session, and it is not a promise that `codex exec` can pause for input.

When the host exposes `request_user_input`, use it for at most 1-3 consequential
alignment decisions and keep the question options in the structured payload.
Do not assume Claude's `AskUserQuestion` schema or Hermes' `clarify` tool name.
When it is absent, ask the questions in the normal conversation and do not
start implementation while the Alignment Checkpoint is open.

Primary sources:

- [Codex request_user_input parameters](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/ToolRequestUserInputParams.json)
- [Codex request_user_input response](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/ToolRequestUserInputResponse.json)
- [Codex app-server round-trip test](https://github.com/openai/codex/blob/main/codex-rs/app-server/tests/suite/v2/request_user_input.rs)
