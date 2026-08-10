from __future__ import annotations

import json
from pathlib import Path

from research_tree.verification_receipts import generate_receipt


def test_receipt_generator_runs_only_registered_command_and_hashes_raw_output(tmp_path: Path) -> None:
    registry = tmp_path / "task-execution.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "groups": [
                    {
                        "group": 1,
                        "depends_on": [],
                        "owner": "quality",
                        "outputs": ["fixture"],
                        "acceptance_command": "python -c \"print('verified')\"",
                        "rollback": "remove fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence" / "group-1.txt"

    receipt = generate_receipt(tmp_path, registry, 1, output, source_revision="a" * 40)

    assert receipt["exit_code"] == 0
    assert receipt["command"] == "python -c \"print('verified')\""
    assert len(receipt["output_digest"]) == 64
    assert "verified" in output.read_text(encoding="utf-8")
