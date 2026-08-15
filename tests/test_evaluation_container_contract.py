"""Static safety contracts for the sealed evaluation-container envelope."""

from __future__ import annotations

from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).parents[1]
DOCKER_ROOT = REPOSITORY_ROOT / "evaluation" / "docker"


def _read(relative_path: str) -> str:
    return (DOCKER_ROOT / relative_path).read_text(encoding="utf-8")


def _service_block(compose: str, service_name: str) -> str:
    match = re.search(
        rf"^  {re.escape(service_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|^[A-Za-z][A-Za-z0-9_-]*:\n|\Z)",
        compose,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing {service_name!r} service"
    return match.group("body")


def test_each_episode_uses_a_new_removed_runner() -> None:
    launcher = _read("run-episode.sh")

    assert "docker compose" in launcher
    assert "run --rm --no-deps" in launcher
    assert "runner" in launcher


def test_runner_is_unprivileged_read_only_and_resource_bounded() -> None:
    compose = _read("compose.yaml")
    runner = _service_block(compose, "runner")

    for required in (
        'user: "65532:65532"',
        "read_only: true",
        "privileged: false",
        "cap_drop:\n      - ALL",
        "security_opt:\n      - no-new-privileges:true",
        "pids_limit: 128",
        "mem_limit: 512m",
        "cpus: 1.0",
        "tmpfs:\n      - /tmp:rw,noexec,nosuid,size=64m",
    ):
        assert required in runner


def test_runner_has_only_internal_broker_connectivity_and_no_sensitive_mounts() -> None:
    compose = _read("compose.yaml")
    runner = _service_block(compose, "runner")

    assert "MODEL_BROKER_URL: http://evaluation-broker:8080" in runner
    assert "ANTHROPIC_BASE_URL: http://evaluation-broker:8080/anthropic" in runner
    assert "ANTHROPIC_API_KEY: broker-managed-placeholder" in runner
    assert "networks:\n      - runner-broker" in runner
    assert "runner-broker:\n    internal: true" in compose
    assert "volumes:" not in runner
    assert "secrets:" not in runner
    assert "docker.sock" not in runner.lower()
    assert "oracle" not in runner.lower()
    assert "deepseek_api_key" not in runner.lower()


def test_broker_alone_receives_secret_file_and_has_fixed_deepseek_destinations() -> None:
    compose = _read("compose.yaml")
    broker = _service_block(compose, "broker")
    broker_source = _read("broker.py")

    assert "secrets:\n      - source: deepseek_api_key" in broker
    assert "DEEPSEEK_API_KEY_FILE: /run/secrets/deepseek_api_key" in broker
    assert "deepseek_api_key:\n    file: ${DEEPSEEK_API_KEY_FILE:-/run/research-tree-no-secret-file}" in compose
    assert "runner-broker" in broker
    assert "broker-egress" in broker
    assert "healthcheck:" in broker
    assert "/healthz" in broker
    assert 'DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"' in broker_source
    assert 'DEEPSEEK_ANTHROPIC_MESSAGES_URL = "https://api.deepseek.com/anthropic/v1/messages"' in broker_source
    assert '"/anthropic/v1/messages": DEEPSEEK_ANTHROPIC_MESSAGES_URL' in broker_source
    assert 'Path("/run/secrets/deepseek_api_key").read_text' in broker_source
    assert "urlopen(request" in broker_source
    assert 'headers["Authorization"] = f"Bearer {self.api_key}"' in broker_source
    assert 'headers["x-api-key"] = self.api_key' in broker_source
    assert 'self.headers.get("Authorization")' not in broker_source
    assert 'self.headers.get("x-api-key")' not in broker_source
    assert "print(" not in broker_source


def test_broker_preserves_anthropic_streaming_without_opening_other_routes() -> None:
    broker_source = _read("broker.py")

    assert "response.headers.get_content_type() == \"text/event-stream\"" in broker_source
    assert "self._stream_response(HTTPStatus(response.status), response)" in broker_source
    assert "response.read(STREAM_CHUNK_BYTES)" in broker_source
    assert 'self.send_header("Transfer-Encoding", "chunked")' in broker_source
    assert 'self.wfile.write(b"0\\r\\n\\r\\n")' in broker_source


def test_images_are_digest_pinned_without_embedding_credentials() -> None:
    for dockerfile_name in ("Dockerfile.runner", "Dockerfile.broker"):
        dockerfile = _read(dockerfile_name)
        assert re.search(r"ARG [A-Z_]+IMAGE=.*@sha256:[0-9a-f]{64}", dockerfile)
        assert "USER 65532:65532" in dockerfile
        assert not re.search(r"(?:API[_-]?KEY|SECRET|TOKEN)\s*=\s*[^$\s]", dockerfile, flags=re.IGNORECASE)


def test_readme_declares_the_daemon_boundary_and_no_secret_logging() -> None:
    readme = _read("README.md")

    for required in (
        "Docker daemon is not a trust boundary",
        "No Docker socket",
        "host home",
        "secret file",
        "not log",
        "claude --version",
        "no provider request",
    ):
        assert required.lower() in readme.lower()
