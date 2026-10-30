# design — plugin-search

Manifest = registry unit (name/capabilities/kinds/description/usage pointer).
`searchProviders` filters manifests by capability/kind/keyword — no usage
bodies in results. `loadUsage` is selection-gated and cached: loading twice
returns the same string (one context entry per provider, measured).
Unselected load attempts are refused mechanically rather than by convention.

## impact_scope

- `rt-core/src/providers/registry.ts` (additive methods); tests
  `rt-core/test/plugin_search.test.ts`; usage stubs
  `rt-core/docs/providers/{anysearch,agent-browser}.md`.

## rejected_designs

- Auto-injecting all provider usages at registry construction (the exact cost
  the ruling rejects).
- Free-form load without selection gating (discipline by convention rots).
- Usage bodies inside manifests (manifests are the cheap surface).
