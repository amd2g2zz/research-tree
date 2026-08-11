# Skill Activation Integrity

Evidence is `discovered` when indexed, `static_ready` when target/package match, and `live_verified` only after an exact native probe. Setup, validation, file reads, links, and bare names never prove live activation.

## Side-effect-free probe

The exact request is `activation-probe v1 <correlation-id>` with a bounded lowercase ASCII id. Return only:

```text
research-tree-activation:v1:<host>:<correlation-id>
```

Do not start research, read task material, call tools, write, delegate, or add Markdown. Extra requests/malformed ids must not emit it.

- Codex app-server `turn/start`: `$research-tree activation-probe ...` text plus typed `{ "type": "skill", "name": "research-tree", "path": ".../SKILL.md" }` input.
- Claude direct: `/research-tree activation-probe ...`; marketplace: `/research-tree:research-tree ...`.
- Hermes after discovery/reload: `/research-tree activation-probe ...`; explicit load: `/skill research-tree ...`.

`scripts/skill_activation.py` constructs/validates without launching a host during construction.

## Evidence boundary

A receipt stores only versions, host, safe correlation, relative package ref, package/body/sentinel digests, and non-proof claims. It excludes prompts, user content, raw output, credentials, absolute home paths, and private reasoning. It does not prove later compliance, correctness, acceptance, delivery, or completion. Missing capability is `unavailable`, never parity success.
