# Codex CLI Compatibility

Use this reference when `research-tree` runs under Codex CLI. The verified
baseline is Codex CLI 0.146.0. Capabilities remain session-dependent; inspect
what the current host exposes instead of calling a tool from another host.

## Native execution

Read `references/codex-native-orchestration.md` before delegation, compaction,
or recovery. It defines the Codex-specific mapping for `AGENTS.md`, plan state,
parallel tool calls, collaboration subagents, artifact verification, and saved
thread recovery.

Codex CLI can resume and fork saved interactive sessions. Those commands restore
conversation state but do not prove that a subprocess, subagent, network call,
or artifact write completed. Workspace state remains authoritative.

Live web search requires the current surface to expose it; in the CLI it can be
enabled with `--search`. Sandbox and approval policy still apply to all other
tools and cannot be widened by a Skill.

## Activation integrity
Codex verification requires the exact text and typed `skill` input defined in `references/skill-activation.md`; text, paths, links, and package checks alone are not live evidence.

## User questions

Codex's app-server protocol defines an experimental `request_user_input`
request. Its payload contains `threadId`, `turnId`, `itemId`, `questions`, and
`isBlocking`; each question can include an `id`, `header`, `question`, and
optional labeled/description options. The client returns an answer map keyed by
question id. The protocol does not make this request available to every CLI
skill session, and it is not a promise that `codex exec` can pause for input.

Use ordinary open-ended dialogue for intent elicitation. When the host exposes
`request_user_input`, reserve it for a rare consequential discrete decision
after the agent has explained the distinction and invited the requester to
express intent in their own words. Keep any resulting options in the structured
payload. Do not assume Claude's `AskUserQuestion` schema or Hermes' `clarify`
tool name. Do not start implementation while the Alignment Checkpoint is open.

## Hooks

Current Codex supports command hooks for session, prompt, tool, permission,
compaction, subagent, and stop events. The repository hook template observes a
small research-specific subset and is opt-in. Hook trust must be reviewed by the
requester; never use `--dangerously-bypass-hook-trust` from this Skill.

Primary sources:

- [Codex request_user_input parameters](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/ToolRequestUserInputParams.json)
- [Codex request_user_input response](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/json/ToolRequestUserInputResponse.json)
- [Codex app-server round-trip test](https://github.com/openai/codex/blob/main/codex-rs/app-server/tests/suite/v2/request_user_input.rs)
- [Codex skills](https://github.com/openai/codex/blob/main/docs/skills.md)
- [Codex hook configuration](https://github.com/openai/codex/blob/main/codex-rs/config/src/hook_config.rs)
- [Codex hook schemas](https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated)
- [Codex CLI](https://github.com/openai/codex)
