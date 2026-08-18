"""Run one host-conformance mode cell and emit a redacted result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from host_conformance import (
    check_negative_oracle,
    check_replay,
    compare_sequences,
    load_case,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--observation", type=Path, help="observed mode run JSON (events, identities, envelope)")
    parser.add_argument("--replay", type=Path, help="replayed persisted-state JSON for comparison")
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args(argv)

    case = load_case(arguments.case)
    result = {
        "schema_version": 1,
        "case_id": case["id"],
        "mode": arguments.mode,
        "status": "blocked",
        "cells": [],
        "replay": {"status": "passed", "divergences": []},
        "blocker": "no observation supplied",
    }
    if arguments.observation is not None:
        observation = json.loads(arguments.observation.read_text(encoding="utf-8"))
        cells = []
        divergences = compare_sequences(case["expected_canonical_sequence"], observation.get("events", []))
        cells.append(
            {
                "name": "normal-run",
                "status": "passed" if not divergences else "failed",
                "detail": "; ".join(divergences) or "expected sequence matched",
                "identities": list(observation.get("identities", [])),
                "events": [str(e) for e in observation.get("events", [])],
            }
        )
        for oracle in observation.get("oracle_submissions", []):
            outcome = check_negative_oracle(case, oracle)
            cells.append({"name": f"oracle:{oracle.get('kind')}", "status": outcome.split(":")[0], "detail": outcome})
        for fault in observation.get("faults", []):
            false_completion = fault.get("resulted_in_completion") is True
            cells.append(
                {
                    "name": f"fault:{fault.get('kind')}",
                    "status": "failed" if false_completion else "passed",
                    "detail": "false completion under fault"
                    if false_completion
                    else "fault resolved without completion",
                }
            )
        result["cells"] = cells
        result["status"] = "passed" if all(c["status"] == "passed" for c in cells) else "failed"
        result["blocker"] = None
        result["envelope"] = observation.get("envelope", {})
    if arguments.replay is not None:
        recorded = json.loads(arguments.observation.read_text(encoding="utf-8")) if arguments.observation else {}
        replayed = json.loads(arguments.replay.read_text(encoding="utf-8"))
        result["replay"] = check_replay(recorded.get("state", {}), replayed)
        if result["replay"]["status"] == "failed":
            result["status"] = "failed"
    arguments.result.parent.mkdir(parents=True, exist_ok=True)
    arguments.result.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "cells": len(result["cells"])}, ensure_ascii=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
