from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_tree.skill_activation import (
    ACTIVATION_STATES,
    ActivationError,
    activation_diagnostic,
    build_activation_probe,
    expected_sentinel,
    run_codex_app_server_probe,
    run_native_probes,
    validate_probe_contract,
    verify_activation_response,
)


HOST_MARKERS = {
    "codex": "research-tree-activation-contract:v1:codex",
    "claude": "research-tree-activation-contract:v1:claude",
    "hermes": "research-tree-activation-contract:v1:hermes",
}


def _package(tmp_path: Path, host: str) -> Path:
    package = tmp_path / host / "research-tree"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        f"---\nname: research-tree\ndescription: test\n---\n\n{HOST_MARKERS[host]}\n",
        encoding="utf-8",
    )
    (package / "references").mkdir()
    (package / "references" / "activation.md").write_text(host, encoding="utf-8")
    return package


def test_activation_states_are_explicit_and_monotonic() -> None:
    assert ACTIVATION_STATES == ("discovered", "static_ready", "live_verified")


def test_codex_probe_requires_text_marker_and_typed_skill_item(tmp_path: Path) -> None:
    package = _package(tmp_path, "codex")
    probe = build_activation_probe(
        "codex",
        package,
        correlation_id="workspace-17",
    )

    assert probe["transport"] == "app_server"
    assert probe["request"]["method"] == "turn/start"
    assert "threadId" not in probe["request"]["params"]
    assert probe["request"]["params"]["input"] == [
        {
            "type": "text",
            "text": "$research-tree activation-probe v1 workspace-17",
        },
        {
            "type": "skill",
            "name": "research-tree",
            "path": str((package / "SKILL.md").resolve()),
        },
    ]


def test_claude_and_hermes_keep_independent_slash_paths(tmp_path: Path) -> None:
    claude = build_activation_probe("claude", _package(tmp_path, "claude"), correlation_id="run-a")
    hermes = build_activation_probe("hermes", _package(tmp_path, "hermes"), correlation_id="run-b")

    assert claude["invocation"] == "/research-tree activation-probe v1 run-a"
    assert claude["alternatives"] == ["/research-tree:research-tree activation-probe v1 run-a"]
    assert hermes["invocation"] == "/research-tree activation-probe v1 run-b"
    assert hermes["alternatives"] == ["/skill research-tree activation-probe v1 run-b"]


@pytest.mark.parametrize(
    ("host", "raw_request"),
    [
        ("codex", "research-tree"),
        ("codex", "$research-tree"),
        ("claude", "[research-tree](C:/checkout/SKILL.md)"),
        ("hermes", "C:/checkout/SKILL.md"),
    ],
)
def test_file_links_bare_names_and_markers_are_not_live(host: str, raw_request: str) -> None:
    diagnostic = activation_diagnostic(host, raw_request)

    assert diagnostic["state"] == "discovered"
    assert diagnostic["code"] == "activation_unverified"
    assert diagnostic["required_invocation"]
    assert diagnostic["live_verified"] is False


def test_wrong_host_and_malformed_codex_probe_are_rejected(tmp_path: Path) -> None:
    probe = build_activation_probe(
        "codex",
        _package(tmp_path, "codex"),
        correlation_id="run-1",
    )

    with pytest.raises(ActivationError, match="wrong_host"):
        validate_probe_contract(probe, expected_host="claude")

    probe["request"]["params"]["input"] = probe["request"]["params"]["input"][:1]
    with pytest.raises(ActivationError, match="typed_skill_input_missing"):
        validate_probe_contract(probe, expected_host="codex")


def test_wrong_host_package_marker_is_rejected(tmp_path: Path) -> None:
    package = _package(tmp_path, "claude")

    with pytest.raises(ActivationError, match="wrong_host_package"):
        build_activation_probe("codex", package, correlation_id="run-2")


def test_exact_sentinel_creates_safe_bounded_receipt(tmp_path: Path) -> None:
    package = _package(tmp_path, "hermes")
    probe = build_activation_probe("hermes", package, correlation_id="workspace-5")
    receipt = verify_activation_response(
        probe,
        expected_sentinel("hermes", "workspace-5"),
        package,
        package_ref="packages/hermes/research-tree",
    )

    assert receipt["state"] == "live_verified"
    assert receipt["host"] == "hermes"
    assert receipt["package_ref"] == "packages/hermes/research-tree"
    assert receipt["package_digest"] == probe["package_digest"]
    assert receipt["skill_body_digest"] == probe["skill_body_digest"]
    assert receipt["does_not_prove"] == [
        "instruction_following",
        "research_correctness",
        "acceptance",
        "delivery",
        "completion",
    ]
    serialized = repr(receipt)
    assert str(package.resolve()) not in serialized
    assert "raw_output" not in receipt
    assert "prompt" not in receipt


def test_extra_output_and_package_drift_cannot_create_receipt(tmp_path: Path) -> None:
    package = _package(tmp_path, "claude")
    probe = build_activation_probe("claude", package, correlation_id="workspace-6")
    sentinel = expected_sentinel("claude", "workspace-6")

    with pytest.raises(ActivationError, match="sentinel_mismatch"):
        verify_activation_response(
            probe,
            f"{sentinel}\nSkill loaded.",
            package,
            package_ref="packages/claude-code/research-tree/skills/research-tree",
        )

    (package / "references" / "activation.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ActivationError, match="package_drift"):
        verify_activation_response(
            probe,
            sentinel,
            package,
            package_ref="packages/claude-code/research-tree/skills/research-tree",
        )


def test_native_probe_results_are_independent_and_unavailable_is_not_passed(tmp_path: Path) -> None:
    probes = {
        host: build_activation_probe(
            host,
            _package(tmp_path, host),
            correlation_id=f"run-{host}",
        )
        for host in HOST_MARKERS
    }

    def find_executable(name: str) -> str | None:
        return None if name == "claude" else f"/tools/{name}"

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=expected_sentinel("hermes", "run-hermes"),
            stderr="",
        )

    def codex_runner(executable: str, probe: object) -> dict[str, object]:
        return {"host": "codex", "status": "live_verified"}

    results = run_native_probes(
        probes,
        executable_finder=find_executable,
        runner=runner,
        codex_runner=codex_runner,
    )

    assert results["codex"]["status"] == "live_verified"
    assert results["hermes"]["status"] == "live_verified"
    assert results["claude"] == {
        "host": "claude",
        "status": "unavailable",
        "missing_capability": "executable:claude",
    }
    assert all(result.get("status") != "passed" for result in results.values())


class _FakeCodexSession:
    def __init__(self, notifications: list[object]) -> None:
        self.notifications = iter(notifications)
        self.calls: list[tuple[str, object]] = []

    def __enter__(self) -> _FakeCodexSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def request(self, method: str, params: object) -> object:
        self.calls.append((method, params))
        responses = {
            "initialize": {"serverInfo": {"name": "codex"}},
            "thread/start": {"thread": {"id": "thread-real"}},
            "turn/start": {"turn": {"id": "turn-real", "status": "inProgress"}},
        }
        if method not in responses:
            raise AssertionError(method)
        return responses[method]

    def notify(self, method: str) -> None:
        self.calls.append((method, None))

    def next_notification(self) -> object:
        return next(self.notifications)


def _codex_notifications(
    *,
    text: str,
    status: str = "completed",
    item_thread: str = "thread-real",
    final_item: bool = True,
) -> list[object]:
    item = {"type": "agentMessage", "id": "item-1", "text": text}
    return [
        {
            "method": "item/completed",
            "params": {"threadId": item_thread, "turnId": "turn-real", "item": item},
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-real",
                "turnId": "turn-real",
                "turn": {"id": "turn-real", "status": status, "items": [item] if final_item else []},
            },
        },
    ]


def test_codex_app_server_uses_full_handshake_and_returned_ids(tmp_path: Path) -> None:
    probe = build_activation_probe("codex", _package(tmp_path, "codex"), correlation_id="run-codex")
    session = _FakeCodexSession(_codex_notifications(text=expected_sentinel("codex", "run-codex")))

    result = run_codex_app_server_probe("codex", probe, session_factory=lambda _: session)

    assert result["status"] == "live_verified"
    assert [method for method, _ in session.calls] == [
        "initialize",
        "initialized",
        "thread/start",
        "turn/start",
    ]
    turn_params = session.calls[-1][1]
    assert turn_params["threadId"] == "thread-real"
    assert turn_params["input"][1]["type"] == "skill"
    thread_params = session.calls[-2][1]
    assert thread_params["ephemeral"] is True
    assert thread_params["sandbox"] == "read-only"
    fallback = _FakeCodexSession(_codex_notifications(text=expected_sentinel("codex", "run-codex"))[1:])
    assert run_codex_app_server_probe("codex", probe, session_factory=lambda _: fallback)["status"] == "live_verified"


@pytest.mark.parametrize(
    ("notifications", "diagnostic"),
    [
        (["research-tree-activation:v1:codex:run-codex"], "protocol_message_invalid"),
        (
            _codex_notifications(
                text="research-tree-activation:v1:codex:run-codex",
                item_thread="wrong-thread",
                final_item=False,
            ),
            "sentinel_mismatch",
        ),
        (_codex_notifications(text="sentinel plus extra text"), "sentinel_mismatch"),
        (_codex_notifications(text="ignored", status="failed"), "native_probe_failed"),
    ],
)
def test_codex_app_server_rejects_unbound_or_inexact_evidence(
    tmp_path: Path,
    notifications: list[object],
    diagnostic: str,
) -> None:
    probe = build_activation_probe("codex", _package(tmp_path, "codex"), correlation_id="run-codex")
    session = _FakeCodexSession(notifications)

    result = run_codex_app_server_probe("codex", probe, session_factory=lambda _: session)

    assert result == {"host": "codex", "status": "failed", "diagnostic": diagnostic}
