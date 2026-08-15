# Design

## Public grammar

The sole public grammar is `research-tree run --workspace PATH <verb>`. The
workspace is required and is passed unchanged to `RunLedger`, which owns the
current SQLite database at `.research-tree/run-ledger.sqlite3`.

| Verb | Required input | Direct coordinator operation |
| --- | --- | --- |
| `ingest` | JSON `--event` HostEvent envelope | `ingest_host_event()` |
| `recover` | `--run-id` | `recover()` |
| `why-not-complete` | `--run-id` | `why_not_complete()` |
| `complete` | `--run-id`, `--actor`, `--expected-revision` | `complete()` |

The CLI does not synthesize revisions, host envelopes, deliveries, acceptance,
or reconciliation observations. In particular, an event is parsed as JSON and
passed directly to the HostEvent-only coordinator ingress; it cannot select the
retired generic ingestion signature.

## JSON and errors

Every coordinator result is emitted as sorted JSON to stdout with the stable
fields `code`, `category`, `retryability`, `run_id`, `safe_message`,
`unmet_obligations`, `evidence_refs`, and `next_action`. Successful responses
use code `ok` and include the operation result. Coordinator stale-revision
errors use exit code 3, completion blocks use 4 with their unmet obligations,
and input/protocol errors use 2. The underlying safe error string is retained
as the response code; no legacy translation is introduced.

Argument parser failures remain normal argparse exit-2 failures. They occur
before a workspace is opened, preserving #164's absence guarantee for retired
commands.

## Delivery boundaries

`CausalTraceService.reconcile_host()` remains a debug-only read projection and
is deliberately not surfaced here. The delivery and acceptance writers are
not coordinator methods, so publishing them would create a composite workflow
outside the verified direct-operation boundary. Rollback is a Git revert; it
does not restore old commands or add a compatibility route.
