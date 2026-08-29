"""Host-specific, bounded evidence for research-tree skill activation."""

from __future__ import annotations

import hashlib
import json
import queue
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

SKILL_NAME = "research-tree"
ACTIVATION_SCHEMA_VERSION = 1
ACTIVATION_PROBE_VERSION = "v1"
ACTIVATION_STATES = ("discovered", "static_ready", "live_verified")
LOADER_SCHEMA_VERSION = 1
LOADER_STATES = ("package_attested", "host_message_verified", "live_verified", "unavailable")
ACTIVATION_GATE_STATES = ("blocked", "ready")
SUPPORTED_HOSTS = ("codex", "claude", "hermes")
HOST_MARKERS = {
    "codex": "research-tree-activation-contract:v1:codex",
    "claude": "research-tree-activation-contract:v1:claude",
    "hermes": "research-tree-activation-contract:v1:hermes",
}
CORRELATION_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class ActivationError(ValueError):
    """Raised when activation evidence is malformed or exceeds its authority."""


def evaluate_activation_gate(
    *,
    loader_state: str,
    alignment_state: str,
    handoff_state: str,
    requested_action: str,
) -> dict[str, object]:
    """Apply the same fail-closed activation state machine for every host."""
    if loader_state not in {"host_message_verified", "live_verified"}:
        return {"state": "blocked", "code": "loader_integrity_unverified"}
    if alignment_state != "equilibrium":
        return {"state": "blocked", "code": "alignment_pending"}
    if handoff_state != "confirmed":
        return {"state": "blocked", "code": "handoff_pending"}
    if requested_action not in {"dispatch", "delegate", "research"}:
        return {"state": "blocked", "code": "unsupported_activation_action"}
    return {"state": "ready", "code": "activation_authorized"}


def build_loader_receipt(
    package_root: Path,
    *,
    host: str,
    session_id: str,
    state: str = "package_attested",
    evidence: str = "static-package",
) -> dict[str, object]:
    """Create a redacted receipt binding one host session to exact skill bytes."""
    selected_host = _host(host)
    correlation = _correlation(session_id)
    if state not in LOADER_STATES or state == "unavailable":
        _fail("invalid_loader_state", "a receipt must carry a verified state")
    root = package_root.expanduser().resolve()
    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        _fail("package_missing", "package root must contain SKILL.md")
    payload = skill_file.read_bytes()
    digests = package_digests(root)
    return {
        "schema_version": LOADER_SCHEMA_VERSION,
        "state": state,
        "host": selected_host,
        "session_id": correlation,
        "package_ref": root.name,
        "package_digest": digests["package_digest"],
        "skill_body_digest": digests["skill_body_digest"],
        "byte_count": len(payload),
        "line_count": len(payload.decode("utf-8").splitlines()),
        "evidence": evidence,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def validate_loader_receipt(
    receipt: Mapping[str, object],
    package_root: Path,
    *,
    host: str,
    session_id: str | None = None,
    require_verified: bool = True,
) -> dict[str, object]:
    """Verify a receipt against current bytes and an optional session identity."""
    selected_host = _host(host)
    if receipt.get("schema_version") != LOADER_SCHEMA_VERSION:
        _fail("invalid_loader_receipt", "unsupported loader receipt schema")
    state = receipt.get("state")
    if state not in LOADER_STATES or state == "unavailable":
        _fail("invalid_loader_receipt", "receipt state is not verifiable")
    if require_verified and state not in {"host_message_verified", "live_verified"}:
        _fail("unverified_loader_integrity", "host-level loader evidence is unavailable")
    if receipt.get("host") != selected_host:
        _fail("invalid_loader_receipt", "receipt host does not match expected host")
    actual_session = _correlation(receipt.get("session_id"))
    if session_id is not None and actual_session != _correlation(session_id):
        _fail("invalid_loader_receipt", "receipt session does not match activation session")
    root = package_root.expanduser().resolve()
    current = package_digests(root)
    skill = root / "SKILL.md"
    payload = skill.read_bytes()
    if receipt.get("package_digest") != current["package_digest"]:
        _fail("invalid_loader_receipt", "package digest does not match current package")
    if receipt.get("skill_body_digest") != current["skill_body_digest"]:
        _fail("invalid_loader_receipt", "skill digest does not match current SKILL.md")
    if receipt.get("byte_count") != len(payload) or receipt.get("line_count") != len(
        payload.decode("utf-8").splitlines()
    ):
        _fail("invalid_loader_receipt", "skill byte or line count does not match current file")
    return dict(receipt)


def loader_integrity_status(
    package_root: Path,
    *,
    host: str,
    receipt: Mapping[str, object] | None = None,
    session_id: str | None = None,
) -> dict[str, object]:
    """Return bounded status without converting missing evidence into a pass."""
    if receipt is None:
        return {"state": "unverified_loader_integrity", "host": _host(host)}
    try:
        validated = validate_loader_receipt(
            receipt,
            package_root,
            host=host,
            session_id=session_id,
            require_verified=False,
        )
    except ActivationError as exc:
        return {"state": "invalid_loader_receipt", "host": _host(host), "diagnostic": str(exc).split(":", 1)[0]}
    return {"state": str(validated["state"]), "host": _host(host), "session_id": validated["session_id"]}


def _fail(code: str, detail: str) -> None:
    raise ActivationError(f"{code}: {detail}")


def _host(value: object) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_HOSTS:
        _fail("unsupported_host", f"expected one of {', '.join(SUPPORTED_HOSTS)}")
    return value


def _correlation(value: object) -> str:
    if not isinstance(value, str) or CORRELATION_RE.fullmatch(value) is None:
        _fail("invalid_correlation", "use 1-64 lowercase ASCII identifier characters")
    return value


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def package_digests(package_root: Path) -> dict[str, str]:
    """Return canonical tree and SKILL.md digests without embedding absolute paths."""
    root = package_root.expanduser().resolve()
    skill_file = root / "SKILL.md"
    if not root.is_dir() or not skill_file.is_file():
        _fail("package_missing", "package root must contain SKILL.md")

    tree = hashlib.sha256()
    files = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if "__pycache__" in relative.parts or candidate.suffix == ".pyc":
            continue
        files.append((relative.as_posix(), candidate))
    for relative, candidate in sorted(files):
        payload = candidate.read_bytes()
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(str(len(payload)).encode("ascii"))
        tree.update(b"\0")
        tree.update(payload)
        tree.update(b"\0")
    return {
        "package_digest": tree.hexdigest(),
        "skill_body_digest": _digest(skill_file.read_bytes()),
    }


def _validate_package_host(package_root: Path, host: str) -> dict[str, str]:
    selected_host = _host(host)
    skill_file = package_root.expanduser().resolve() / "SKILL.md"
    try:
        skill_body = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _fail("package_missing", f"could not read UTF-8 SKILL.md: {exc}")
    marker = HOST_MARKERS[selected_host]
    if marker not in skill_body:
        foreign = [
            candidate for name, candidate in HOST_MARKERS.items() if name != selected_host and candidate in skill_body
        ]
        detail = "package contains another host marker" if foreign else "required host marker is missing"
        _fail("wrong_host_package", detail)
    return package_digests(package_root)


def expected_sentinel(host: str, correlation_id: str) -> str:
    return f"research-tree-activation:{ACTIVATION_PROBE_VERSION}:{_host(host)}:{_correlation(correlation_id)}"


def _invocation(host: str, correlation_id: str) -> str:
    prefix = "$research-tree" if host == "codex" else "/research-tree"
    return f"{prefix} activation-probe {ACTIVATION_PROBE_VERSION} {correlation_id}"


def build_activation_probe(
    host: str,
    package_root: Path,
    *,
    correlation_id: str,
) -> dict[str, object]:
    """Construct a native probe contract without launching a host or writing state."""
    selected_host = _host(host)
    correlation = _correlation(correlation_id)
    root = package_root.expanduser().resolve()
    digests = _validate_package_host(root, selected_host)
    probe: dict[str, object] = {
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "probe_version": ACTIVATION_PROBE_VERSION,
        "host": selected_host,
        "correlation_id": correlation,
        "package_digest": digests["package_digest"],
        "skill_body_digest": digests["skill_body_digest"],
        "expected_sentinel": expected_sentinel(selected_host, correlation),
    }
    invocation = _invocation(selected_host, correlation)
    if selected_host == "codex":
        probe.update(
            {
                "transport": "app_server",
                "request": {
                    "method": "turn/start",
                    "params": {
                        "input": [
                            {"type": "text", "text": invocation},
                            {
                                "type": "skill",
                                "name": SKILL_NAME,
                                "path": str((root / "SKILL.md").resolve()),
                            },
                        ],
                    },
                },
            }
        )
    elif selected_host == "claude":
        probe.update(
            {
                "transport": "slash_skill",
                "invocation": invocation,
                "alternatives": [
                    f"/research-tree:research-tree activation-probe {ACTIVATION_PROBE_VERSION} {correlation}"
                ],
            }
        )
    else:
        probe.update(
            {
                "transport": "slash_skill",
                "invocation": invocation,
                "alternatives": [f"/skill research-tree activation-probe {ACTIVATION_PROBE_VERSION} {correlation}"],
            }
        )
    return probe


def validate_probe_contract(probe: Mapping[str, object], *, expected_host: str) -> None:
    selected_host = _host(expected_host)
    if probe.get("schema_version") != ACTIVATION_SCHEMA_VERSION:
        _fail("unsupported_schema", "activation schema version does not match")
    if probe.get("probe_version") != ACTIVATION_PROBE_VERSION:
        _fail("unsupported_probe", "activation probe version does not match")
    if probe.get("host") != selected_host:
        _fail("wrong_host", "probe host does not match expected host")
    correlation = _correlation(probe.get("correlation_id"))
    if probe.get("expected_sentinel") != expected_sentinel(selected_host, correlation):
        _fail("sentinel_contract_mismatch", "expected sentinel is not canonical")
    for field in ("package_digest", "skill_body_digest"):
        value = probe.get(field)
        if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
            _fail("invalid_digest", f"{field} must be lowercase SHA-256")

    invocation = _invocation(selected_host, correlation)
    if selected_host == "codex":
        request = probe.get("request")
        if not isinstance(request, Mapping) or request.get("method") != "turn/start":
            _fail("codex_turn_start_missing", "Codex probe requires turn/start")
        params = request.get("params")
        if not isinstance(params, Mapping) or "threadId" in params:
            _fail("codex_thread_prebound", "Codex probe threads must come from thread/start")
        items = params.get("input")
        if not isinstance(items, list):
            _fail("typed_skill_input_missing", "Codex input must include typed skill data")
        text_items = [item for item in items if isinstance(item, Mapping) and item.get("type") == "text"]
        skill_items = [item for item in items if isinstance(item, Mapping) and item.get("type") == "skill"]
        if len(text_items) != 1 or text_items[0].get("text") != invocation:
            _fail("codex_text_marker_invalid", "Codex text marker is missing or malformed")
        if len(skill_items) != 1:
            _fail("typed_skill_input_missing", "Codex requires exactly one typed skill input")
        skill_item = skill_items[0]
        if skill_item.get("name") != SKILL_NAME or not str(skill_item.get("path", "")).endswith("SKILL.md"):
            _fail("typed_skill_input_invalid", "Codex skill name or path is invalid")
    elif probe.get("invocation") != invocation:
        _fail("slash_invocation_invalid", f"{selected_host} requires its native slash invocation")


def _safe_package_ref(value: str) -> str:
    if "\\" in value:
        _fail("unsafe_package_ref", "package_ref must use forward slashes")
    reference = PurePosixPath(value)
    if reference.is_absolute() or not reference.parts or ".." in reference.parts:
        _fail("unsafe_package_ref", "package_ref must be a relative package path")
    return reference.as_posix()


def verify_activation_response(
    probe: Mapping[str, object],
    observed_output: str,
    package_root: Path,
    *,
    package_ref: str,
) -> dict[str, object]:
    """Validate an exact native sentinel and return a deliberately bounded receipt."""
    host = _host(probe.get("host"))
    validate_probe_contract(probe, expected_host=host)
    current = _validate_package_host(package_root, host)
    if any(probe.get(field) != current[field] for field in current):
        _fail("package_drift", "package or SKILL.md changed after probe construction")
    if host == "codex":
        request = probe["request"]
        assert isinstance(request, Mapping)
        params = request["params"]
        assert isinstance(params, Mapping)
        items = params["input"]
        assert isinstance(items, list)
        skill_item = next(item for item in items if isinstance(item, Mapping) and item.get("type") == "skill")
        expected_path = str((package_root.expanduser().resolve() / "SKILL.md").resolve())
        if skill_item.get("path") != expected_path:
            _fail("package_drift", "typed skill path no longer matches the package")
    expected = str(probe["expected_sentinel"])
    normalized = observed_output.replace("\r\n", "\n").replace("\r", "\n")
    if normalized != expected:
        _fail("sentinel_mismatch", "host output was not the exact activation sentinel")
    return {
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "probe_version": ACTIVATION_PROBE_VERSION,
        "state": "live_verified",
        "host": host,
        "workspace_correlation": _correlation(probe.get("correlation_id")),
        "package_ref": _safe_package_ref(package_ref),
        "package_digest": current["package_digest"],
        "skill_body_digest": current["skill_body_digest"],
        "sentinel_digest": _digest(expected.encode("utf-8")),
        "does_not_prove": [
            "instruction_following",
            "research_correctness",
            "acceptance",
            "delivery",
            "completion",
        ],
    }


def activation_diagnostic(host: str, request: object) -> dict[str, object]:
    """Explain why ordinary text or file references are not live activation evidence."""
    selected_host = _host(host)
    required = {
        "codex": "$research-tree plus typed skill input in app-server turn/start",
        "claude": "/research-tree",
        "hermes": "/research-tree or /skill research-tree",
    }[selected_host]
    return {
        "host": selected_host,
        "state": "discovered",
        "code": "activation_unverified",
        "required_invocation": required,
        "live_verified": False,
    }


class _CodexAppServerSession:
    def __init__(self, executable: str, *, timeout: float = 120) -> None:
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        self.process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.messages: queue.Queue[object] = queue.Queue()
        self.pending: list[Mapping[str, object]] = []
        self.request_id = 0
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                message = line.rstrip("\r\n")
            self.messages.put(message)
        self.messages.put(None)

    def _read(self) -> Mapping[str, object]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("codex app-server", self.timeout)
        try:
            message = self.messages.get(timeout=remaining)
        except queue.Empty as exc:
            raise subprocess.TimeoutExpired("codex app-server", self.timeout) from exc
        if message is None:
            _fail("protocol_closed", "app-server stdout closed before completion")
        if not isinstance(message, Mapping):
            _fail("protocol_message_invalid", "app-server stdout must be JSON-RPC objects")
        return message

    def _write(self, message: Mapping[str, object]) -> None:
        if self.process.stdin is None:
            _fail("protocol_closed", "app-server stdin is unavailable")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: object) -> object:
        request_id = self.request_id
        self.request_id += 1
        self._write({"id": request_id, "method": method, "params": params})
        while True:
            message = self._read()
            if message.get("id") != request_id:
                self.pending.append(message)
                continue
            if "error" in message:
                _fail("protocol_request_failed", method)
            return message.get("result")

    def notify(self, method: str) -> None:
        self._write({"method": method})

    def next_notification(self) -> object:
        if self.pending:
            return self.pending.pop(0)
        return self._read()

    def __enter__(self) -> _CodexAppServerSession:
        return self

    def __exit__(self, *args: object) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(code, "app-server response shape is invalid")
    return value


def _agent_message(item: object) -> tuple[str, str] | None:
    if not isinstance(item, Mapping) or item.get("type") != "agentMessage":
        return None
    item_id = item.get("id")
    text = item.get("text")
    if not isinstance(item_id, str) or not isinstance(text, str):
        _fail("protocol_message_invalid", "agentMessage requires string id and text")
    return item_id, text


def run_codex_app_server_probe(
    executable: str,
    probe: Mapping[str, object],
    *,
    session_factory: Callable[[str], object] = _CodexAppServerSession,
) -> dict[str, object]:
    """Run one Codex probe through a correlated app-server lifecycle."""
    validate_probe_contract(probe, expected_host="codex")
    try:
        with session_factory(executable) as session:
            session.request(
                "initialize",
                {"clientInfo": {"name": "research-tree", "title": "Research Tree", "version": "1"}},
            )
            session.notify("initialized")
            request = _mapping(probe["request"], "codex_turn_start_missing")
            template = _mapping(request["params"], "codex_turn_start_missing")
            skill_path = next(item["path"] for item in template["input"] if item["type"] == "skill")
            thread_result = _mapping(
                session.request(
                    "thread/start",
                    {
                        "cwd": str(Path(skill_path).parent),
                        "approvalPolicy": "never",
                        "sandbox": "read-only",
                        "ephemeral": True,
                    },
                ),
                "codex_thread_start_invalid",
            )
            thread = _mapping(thread_result.get("thread"), "codex_thread_start_invalid")
            thread_id = thread.get("id")
            if not isinstance(thread_id, str) or not thread_id:
                _fail("codex_thread_start_invalid", "thread/start did not return an id")
            turn_params = {**template, "threadId": thread_id}
            turn_result = _mapping(
                session.request("turn/start", turn_params),
                "codex_turn_start_invalid",
            )
            turn = _mapping(turn_result.get("turn"), "codex_turn_start_invalid")
            turn_id = turn.get("id")
            if not isinstance(turn_id, str) or turn.get("status") != "inProgress":
                _fail("codex_turn_start_invalid", "turn/start did not return an in-progress turn")
            messages: dict[str, str] = {}
            while True:
                event = _mapping(session.next_notification(), "protocol_message_invalid")
                params = event.get("params")
                if not isinstance(params, Mapping):
                    continue
                if event.get("method") == "item/completed":
                    if params.get("threadId") == thread_id and params.get("turnId") == turn_id:
                        agent = _agent_message(params.get("item"))
                        if agent is not None:
                            messages[agent[0]] = agent[1]
                    continue
                if event.get("method") != "turn/completed":
                    continue
                completed = _mapping(params.get("turn"), "codex_turn_completed_invalid")
                if completed.get("id") != turn_id:
                    continue
                if params.get("threadId", thread_id) != thread_id or params.get("turnId", turn_id) != turn_id:
                    continue
                if completed.get("status") != "completed":
                    return {"host": "codex", "status": "failed", "diagnostic": "native_probe_failed"}
                for item in completed.get("items", []):
                    agent = _agent_message(item)
                    if agent is not None:
                        messages[agent[0]] = agent[1]
                expected = probe["expected_sentinel"]
                if list(messages.values()) != [expected]:
                    return {"host": "codex", "status": "failed", "diagnostic": "sentinel_mismatch"}
                return {
                    "host": "codex",
                    "status": "live_verified",
                    "package_digest": probe["package_digest"],
                    "skill_body_digest": probe["skill_body_digest"],
                    "workspace_correlation": probe["correlation_id"],
                }
    except (ActivationError, OSError, StopIteration, subprocess.SubprocessError) as exc:
        diagnostic = str(exc).split(":", 1)[0] if isinstance(exc, ActivationError) else type(exc).__name__
        if diagnostic == "protocol_closed":
            return {"host": "codex", "status": "unavailable", "missing_capability": "surface:app-server-stdio"}
        return {"host": "codex", "status": "failed", "diagnostic": diagnostic}


def run_native_probes(
    probes: Mapping[str, Mapping[str, object]],
    *,
    executable_finder: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., object] = subprocess.run,
    codex_runner: Callable[[str, Mapping[str, object]], dict[str, object]] = run_codex_app_server_probe,
) -> dict[str, dict[str, object]]:
    """Run explicitly supplied probes independently and return only bounded results."""
    results: dict[str, dict[str, object]] = {}
    for host in SUPPORTED_HOSTS:
        if host not in probes:
            continue
        probe = probes[host]
        validate_probe_contract(probe, expected_host=host)
        executable_name = {"codex": "codex", "claude": "claude", "hermes": "hermes"}[host]
        executable = executable_finder(executable_name)
        if executable is None:
            results[host] = {
                "host": host,
                "status": "unavailable",
                "missing_capability": f"executable:{executable_name}",
            }
            continue
        if host == "codex":
            results[host] = codex_runner(executable, probe)
            continue
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "check": False,
            "timeout": 120,
        }
        if host == "claude":
            command = [executable, "-p", str(probe["invocation"])]
        else:
            command = [executable, "-z", str(probe["invocation"])]
        try:
            completed = runner(command, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            results[host] = {
                "host": host,
                "status": "failed",
                "diagnostic": type(exc).__name__,
            }
            continue
        returncode = getattr(completed, "returncode", None)
        stdout = getattr(completed, "stdout", "") or ""
        if returncode != 0:
            results[host] = {
                "host": host,
                "status": "failed",
                "diagnostic": "native_probe_failed",
            }
        elif stdout.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") == probe["expected_sentinel"]:
            results[host] = {
                "host": host,
                "status": "live_verified",
                "package_digest": probe["package_digest"],
                "skill_body_digest": probe["skill_body_digest"],
                "workspace_correlation": probe["correlation_id"],
            }
        else:
            results[host] = {
                "host": host,
                "status": "failed",
                "diagnostic": "sentinel_mismatch",
            }
    return results
