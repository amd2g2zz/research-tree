# Sealed Evaluation Container Envelope

This directory is a Compose contract for a trusted evaluation orchestrator. It
contains no episode input, oracle body, reference patch, provider transcript,
or credential. Building the images, running `docker compose config`, and
starting the broker do not issue a model request. The broker contacts DeepSeek
only after a runner sends a request to its one supported local route.

## Invocation

The trusted orchestrator supplies a Docker-host secret file path without
placing that file in this repository or in an environment variable containing
the credential. It first starts the broker, invokes exactly one fresh runner
for an episode, and tears the broker down when the evaluation scope ends.

```sh
export DEEPSEEK_API_KEY_FILE=/trusted/path/outside/the/repository
docker compose --project-directory evaluation/docker --file evaluation/docker/compose.yaml up --detach broker source-broker
evaluation/docker/run-episode.sh python -m evaluator.run_episode --input -
docker compose --project-directory evaluation/docker --file evaluation/docker/compose.yaml down
```

`run-episode.sh` uses `docker compose run --rm --no-deps runner`, so every
episode receives a new runner container and the container is removed when its
command exits. The script intentionally does not start dependencies; the
orchestrator must have started the model broker and source-broker and may add
its own readiness wait. No runner should be started with `docker compose up`.

## Provider-Free Smoke

The following smoke uses an empty temporary Docker secret file, starts the
broker in its fail-closed unconfigured mode, and runs the Claude Code version
command. It makes no provider request and does not persist or use a credential.
The three image variables must name organization-approved runner, model-broker,
and source-broker images by immutable digest; the runner image must include the
`claude` CLI.

```sh
empty_secret_file=$(mktemp)
trap 'rm -f "$empty_secret_file"' EXIT
export DEEPSEEK_API_KEY_FILE="$empty_secret_file"
export EVALUATION_RUNNER_IMAGE='registry.example/claude-code-runner@sha256:REPLACE_WITH_64_HEX_DIGEST'
export EVALUATION_BROKER_IMAGE='registry.example/evaluation-broker@sha256:REPLACE_WITH_64_HEX_DIGEST'
export EVALUATION_SOURCE_BROKER_IMAGE='registry.example/source-broker@sha256:REPLACE_WITH_64_HEX_DIGEST'
docker compose --project-directory evaluation/docker --file evaluation/docker/compose.yaml up --build --wait broker source-broker
evaluation/docker/run-episode.sh claude --version
docker compose --project-directory evaluation/docker --file evaluation/docker/compose.yaml down
```

An empty secret makes every `POST /v1/chat/completions` return `503` before any
outbound request. The same is true for `POST /anthropic/v1/messages`. This
exercises the runner-to-broker path without allowing a provider call. A real
cost pilot still needs separately authorized, redacted operator runbooks; this
envelope deliberately does not invoke a model by itself.

Before use, the trusted image build pipeline must replace the three placeholder
image digests through `EVALUATION_RUNNER_IMAGE`, `EVALUATION_BROKER_IMAGE`, and
`EVALUATION_SOURCE_BROKER_IMAGE`. Each replacement must be an immutable image
reference containing `@sha256:`. The checked-in placeholders are syntactically
fixed digest values, not image names that resolve to a mutable tag during
evaluation.

## Boundary

The runner is non-root, has a read-only root filesystem, drops every Linux
capability, enables `no-new-privileges`, uses a small writable `/tmp`, and has
CPU, memory, and process limits. No Docker socket, volume mount, host home,
oracle material, or provider key is available to it. Its only configured
model endpoint is the broker on the internal `runner-broker` network. Its only
research endpoint is source-broker on the internal `source-broker` network.
Both networks are Docker `internal`, so the runner has no direct external
route. `/home/runner` is a small writable tmpfs rather than a host home or a
persisted volume.

For Claude Code, the runner uses the non-secret
`ANTHROPIC_BASE_URL=http://evaluation-broker:8080/anthropic` and an explicitly
non-sensitive `ANTHROPIC_API_KEY` placeholder. The broker replaces that
runner-supplied authentication with its own secret only for the fixed DeepSeek
Anthropic-compatible route.

Only the broker receives the Docker secret file at
`/run/secrets/deepseek_api_key`. The broker reads it without printing it,
accepts only `POST /v1/chat/completions` and `POST /anthropic/v1/messages` from
the runner, ignores runner-supplied authorization headers, and forwards only to
`https://api.deepseek.com/chat/completions` or
`https://api.deepseek.com/anthropic/v1/messages`. Anthropic SSE responses are
streamed to the runner with HTTP chunked encoding. It does not log the secret
file, the credential, or request headers. The broker has a separate egress
network; the runner does not.

## Public Source Capture

Live research uses `GET` or `HEAD` against
`http://source-broker:8081/capture?url=<percent-encoded-public-https-url>`.
The source-broker is the only service connected to `source-egress`; it allows
only public HTTPS URLs on port 443. It rejects localhost, private, link-local,
metadata, multicast, reserved, and other non-global addresses. Each DNS result
is validated and the HTTPS connection is pinned to that resolved address with
TLS hostname verification, preventing a DNS rebind between validation and
connect.

Redirects are followed manually with the same URL and DNS validation at every
hop. Captures are bounded to four redirects, one MiB, ten seconds, four
concurrent requests, and 64 requests per source-broker lifecycle. The broker
never forwards runner cookies, authorization, or arbitrary request headers.

Only the source-broker mounts the evaluator-owned `source-captures` Docker
volume. It records capture metadata in a redacted receipt (timestamp, final
URL, status, byte count, content hash, and content reference) and the raw
response body under a content-addressed filename. This supports post-live
replay and audit without preloading the runner. The broker never exposes the
receipt or volume back to the runner, redacts sensitive query values from
persisted URLs, and does not mount or reveal another evaluation arm or oracle.
The named Docker volume is outside the Git worktree, so no source capture is
tracked in Git.

## Synthetic User Proxy

When an episode needs adaptive user interaction, the trusted evaluator starts
the optional `synthetic-user` Compose profile. It mounts an evaluator-owned
synthetic-user bundle as a Docker secret in `user-simulator`; the bundle has
only task-agnostic persona system prompts, opaque conversation identifiers,
assignment commitments, and leak canaries. It contains no task context,
reference answer, scorer rubric, host, arm, or condition. It is not mounted
into the runner, source-broker, model broker, host, or Git worktree.

The runner can call only `POST http://user-simulator:8082/turn` with an opaque
conversation ID, sequential turn number, and its own most recent message. The
simulator receives no host, arm, candidate revision, scorer result, reference
answer, task context, or source capture. It calls DeepSeek V4 Flash through the
internal model broker and returns only a validated JSON user message and
disposition. Each opaque conversation accepts a single strictly sequential turn
stream; a failed or repeated turn cannot be sampled again. Any canary-bearing
or non-JSON turn is rejected. This is a synthetic-user proxy, not
human-experience evidence. A separate blinded reviewer, not the simulator,
assigns any quality score.

Docker daemon is not a trust boundary. Anyone able to control the Docker daemon
or the trusted host orchestrator can inspect or replace containers, images,
networks, and secret mounts. This envelope protects a runner from ordinary
container-level escape paths and accidental host exposure; it does not protect
against a hostile daemon, a privileged host user, or an untrusted orchestrator.

The orchestrator owns lifecycle cleanup, public episode input delivery, result
collection, and any provider billing or rate policy. It must keep request and
result logs redacted and must not record credentials.

## Sealed Episode Execution

The evaluator first writes the sealed manifest, the journal HMAC key, and one
public runner-input JSON file per episode under an ignored
`.research-tree/evaluation-runs/<run-id>/` directory. Each cell's frozen host
command contains exactly one `{episode_input_path}` and
`{episode_output_path}` placeholder. The evaluator then invokes
`evaluation/harness/run_sealed_episodes.py`; it verifies every command and
input digest before launch, records stdout/stderr and the host result only in
that ignored run directory, and checkpoints the HMAC-linked journal.

An interrupted or failed cell invalidates its full task/repeat/role group
across all six host/condition arms. Resume always starts fresh containers for
the full group; it never resumes an agent process in place or mixes stale and
fresh cells in a paired comparison.
