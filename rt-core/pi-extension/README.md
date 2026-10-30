# rt-core pi extension

Mounts rt-core into a pi host session (issue #552). On load it runs the
fake-research e2e walk (deterministic, no LLM calls) and writes
`.research-tree/e2e-marker.json`; it registers the `rt_research` tool for
LLM-driven sessions.

Install: `pi install <this directory>` (or `pi -e index.ts` for a session).
Requires the pi-subagents extension (default-installed by #588 setup).
