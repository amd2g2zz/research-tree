# rt-core-event-log — tasks

- [x] 1. Scaffold: pnpm package, tsconfig (strict), vitest, CI node job
- [x] 2. `events/`: canonical JSON, table-driven schemas, validation (RED→GREEN)
- [x] 3. `store/ledger.ts`: migration registry, hash-chained event log, chain verify
- [ ] 4. `graph/projection.ts` (part 2/2): SQLite adjacency projection, pending edges, rebuild
- [x] 5. `store/engine.ts`: fail-closed dual-write mediator + resync self-heal
- [x] 6. Full local gates (tsc, vitest, legacy Python suite untouched) + PR
