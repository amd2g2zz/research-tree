"""Tests for labeled CLI output (issue #440, tasks.md 2.1).

Every CLI stdout emission — success or failure — must be a balanced
``<rt:tool-output>`` / ``<rt:error>`` XML pair whose inner content parses as
JSON and carries the versioned contract fields.
"""

from __future__ import annotations

import json
import re

from research_tree import cli

OPEN_RE = re.compile(r"<rt:tool-output ([^>]*)>")
CLOSE = "</rt:tool-output>"
ERROR_OPEN_RE = re.compile(r"<rt:error ([^>]*)>")
ERROR_CLOSE = "</rt:error>"


def _attributes(raw: str) -> dict[str, str]:
    return dict(re.findall(r'(\w[\w-]*)="([^"]*)"', raw))


def test_emit_wraps_payload_in_balanced_tool_output_tag(capsys) -> None:
    cli._emit({"schema_version": 1, "contract": "research-tree-lifecycle", "command": "status"})
    out = capsys.readouterr().out
    open_match = OPEN_RE.search(out)
    assert open_match, out
    assert out.endswith(CLOSE + "\n")
    attrs = _attributes(open_match.group(1))
    assert attrs["source"] == "research-tree-cli"
    assert attrs["command"] == "status"
    inner = out[open_match.end() : -len(CLOSE) - 1]
    assert json.loads(inner)  # inner content parses as JSON


def test_emit_escapes_attribute_values(capsys) -> None:
    cli._emit({"command": 'we"ird'})
    out = capsys.readouterr().out
    assert 'we"ird' not in out.split("command=")[1][:8]
    assert "&quot;" in out


def test_failure_envelope_is_labeled_and_versioned(capsys) -> None:
    error = cli.CliInputError("event_json_invalid")
    exit_code, payload = cli._failure(error, None)
    assert exit_code == 2
    assert payload["schema_version"]
    assert payload["contract"] == "research-tree-lifecycle"


def test_failure_output_wrapped_in_rt_error_tag(monkeypatch, capsys, tmp_path) -> None:
    def _boom(_arguments):
        raise cli.CliInputError("event_json_invalid")

    monkeypatch.setattr(cli, "_status", _boom)
    exit_code = cli.main(
        [
            "status",
            "--workspace",
            str(tmp_path / "ws"),
            "--host",
            "codex",
            "--project-id",
            "proj-x",
            "--run-id",
            "run-x",
        ]
    )
    assert exit_code == 2
    out = capsys.readouterr().out
    open_match = ERROR_OPEN_RE.search(out)
    assert open_match, out
    assert out.rstrip().endswith(ERROR_CLOSE)
    attrs = _attributes(open_match.group(1))
    assert attrs["source"] == "research-tree-cli"
    assert "exit-code" in attrs
    assert "category" in attrs
    inner_start = open_match.end()
    inner = out[inner_start : out.rindex(ERROR_CLOSE)]
    parsed = json.loads(inner)
    assert parsed["schema_version"]
    assert parsed["contract"] == "research-tree-lifecycle"


def test_success_output_still_parses_as_tagged_json(capsys) -> None:
    cli._emit(cli._success("run-x", {"ok": True}))
    out = capsys.readouterr().out
    open_match = OPEN_RE.search(out)
    assert open_match
    inner = out[open_match.end() : out.rindex(CLOSE)]
    parsed = json.loads(inner)
    assert parsed["code"] == "ok"
