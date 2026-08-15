"""Static safety contracts for the sealed evaluation-container envelope."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest


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


def _source_broker_module():
    module_name = "research_tree_source_broker_contract"
    module_path = DOCKER_ROOT / "source_broker.py"
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    return module


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
        "HOME: /home/runner",
        "tmpfs:\n      - /tmp:rw,noexec,nosuid,size=64m",
        "- /home/runner:rw,noexec,nosuid,size=64m,uid=65532,gid=65532",
    ):
        assert required in runner


def test_runner_has_only_internal_broker_connectivity_and_no_sensitive_mounts() -> None:
    compose = _read("compose.yaml")
    runner = _service_block(compose, "runner")

    assert "MODEL_BROKER_URL: http://evaluation-broker:8080" in runner
    assert "ANTHROPIC_BASE_URL: http://evaluation-broker:8080/anthropic" in runner
    assert "aliases:\n          - evaluation-broker" in compose
    assert "ANTHROPIC_API_KEY: broker-managed-placeholder" in runner
    assert "SOURCE_BROKER_URL: http://source-broker:8081" in runner
    assert "networks:\n      - runner-broker\n      - source-broker" in runner
    assert "runner-broker:\n    internal: true" in compose
    assert "source-broker:\n    internal: true" in compose
    assert "source-egress" not in runner
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


def test_source_broker_is_the_only_capture_egress_service() -> None:
    compose = _read("compose.yaml")
    source_broker = _service_block(compose, "source-broker")

    for required in (
        'user: "65532:65532"',
        "read_only: true",
        "privileged: false",
        "cap_drop:\n      - ALL",
        "security_opt:\n      - no-new-privileges:true",
        "pids_limit: 64",
        "mem_limit: 256m",
        "cpus: 0.5",
        'expose:\n      - "8081"',
        "source-captures:/var/lib/research-tree/source-captures",
        "source-broker",
        "source-egress",
    ):
        assert required in source_broker
    assert "ports:" not in source_broker
    assert "secrets:" not in source_broker
    assert "source-captures:" in compose


def test_source_broker_enforces_public_https_and_pins_dns_results() -> None:
    source_broker = _read("source_broker.py")

    for required in (
        'ALLOWED_METHODS = frozenset({"GET", "HEAD"})',
        "MAX_REDIRECTS = 4",
        "MAX_CAPTURE_BYTES = 1 * 1024 * 1024",
        "MAX_CONCURRENT_CAPTURES = 4",
        "MAX_CAPTURE_REQUESTS = 64",
        "socket.getaddrinfo",
        "ipaddress.ip_address",
        "if not address.is_global:",
        "class PinnedHTTPSConnection(HTTPSConnection):",
        "socket.create_connection((self._pinned_address, self.port)",
        "server_hostname=self.host",
        "urljoin",
        "REDIRECT_STATUS_CODES",
        "HTTPStatus.METHOD_NOT_ALLOWED",
    ):
        assert required in source_broker
    assert "urlopen(" not in source_broker


def test_source_capture_is_evaluator_only_and_preserves_replayable_bytes() -> None:
    compose = _read("compose.yaml")
    source_broker = _read("source_broker.py")

    assert 'SOURCE_CAPTURE_DIR = Path("/var/lib/research-tree/source-captures")' in source_broker
    assert (
        'CAPTURE_METADATA_KEYS = ("captured_at", "final_url", "content_sha256", "content_ref", "status", "bytes")'
        in source_broker
    )
    assert "SENSITIVE_QUERY_MARKERS" in source_broker
    assert "_metadata_url" in source_broker
    assert "os.replace" in source_broker
    assert "path.chmod(0o600)" in source_broker
    assert "source-captures" in compose
    runner = _service_block(compose, "runner")
    assert "source-capture-metadata" not in runner
    assert "SOURCE_CAPTURE_METADATA_DIR" not in runner


def test_source_broker_rejects_private_mixed_dns_and_non_https_destinations(monkeypatch) -> None:
    source_broker = _source_broker_module()

    for url in (
        "http://example.com/article",
        "https://example.com:444/article",
        "https://localhost/article",
        "https://user:password@example.com/article",
    ):
        with pytest.raises(source_broker.BlockedSource):
            source_broker._normalize_public_https_url(url)

    def mixed_answers(*arguments, **keyword_arguments):
        del arguments, keyword_arguments
        return [
            (source_broker.socket.AF_INET, source_broker.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (source_broker.socket.AF_INET, source_broker.socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
        ]

    monkeypatch.setattr(source_broker.socket, "getaddrinfo", mixed_answers)
    with pytest.raises(source_broker.BlockedSource):
        source_broker._resolve_public_addresses("example.test")


def test_source_broker_persists_redacted_metadata_and_replayable_content(tmp_path: Path) -> None:
    source_broker = _source_broker_module()
    metadata_url = source_broker._metadata_url("https://example.test/article?topic=proxy&api_key=secret-value")

    assert "topic=proxy" in metadata_url
    assert "api_key=REDACTED" in metadata_url
    assert "secret-value" not in metadata_url

    store = source_broker.CaptureMetadataStore(tmp_path)
    body = b"replayable research content"
    store.record(
        {
            "captured_at": "2026-08-15T00:00:00+00:00",
            "final_url": metadata_url,
            "content_sha256": "sha256:" + source_broker.sha256(body).hexdigest(),
            "status": 200,
            "bytes": len(body),
        },
        body,
    )

    metadata_files = tuple((tmp_path / "metadata").glob("capture-*.json"))
    assert len(metadata_files) == 1
    payload = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert set(payload) == {"captured_at", "final_url", "content_sha256", "content_ref", "status", "bytes"}
    assert payload["content_ref"].startswith("content/")
    assert (tmp_path / payload["content_ref"]).read_bytes() == body
    assert metadata_files[0].stat().st_mode & 0o777 == 0o600


def test_broker_preserves_anthropic_streaming_without_opening_other_routes() -> None:
    broker_source = _read("broker.py")

    assert 'response.headers.get_content_type() == "text/event-stream"' in broker_source
    assert "self._stream_response(HTTPStatus(response.status), response)" in broker_source
    assert "response.read(STREAM_CHUNK_BYTES)" in broker_source
    assert 'self.send_header("Transfer-Encoding", "chunked")' in broker_source
    assert 'self.wfile.write(b"0\\r\\n\\r\\n")' in broker_source


def test_images_are_digest_pinned_without_embedding_credentials() -> None:
    for dockerfile_name in ("Dockerfile.runner", "Dockerfile.broker", "Dockerfile.source-broker"):
        dockerfile = _read(dockerfile_name)
        assert re.search(r"ARG [A-Z_]+IMAGE=.*@sha256:[0-9a-f]{64}", dockerfile)
        assert "USER 65532:65532" in dockerfile
        assert not re.search(r"(?:API[_-]?KEY|SECRET|TOKEN)\s*=\s*[^$\s]", dockerfile, flags=re.IGNORECASE)


def test_runner_image_creation_is_idempotent_for_trusted_host_images() -> None:
    dockerfile = _read("Dockerfile.runner")

    assert "getent group runner" in dockerfile
    assert "id -u runner" in dockerfile


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
        "source-broker",
        "public HTTPS",
        "DNS rebind",
        "capture metadata",
        "EVALUATION_SOURCE_BROKER_IMAGE",
    ):
        assert required.lower() in readme.lower()
