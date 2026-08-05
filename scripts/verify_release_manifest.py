"""Verify the versioned alpha2 release manifest without proxy metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"manifest_version", "source_revision", "created_at", "schema_versions", "host_packages", "commands", "evaluations", "gates", "limitations", "verifier"}
HOSTS = {"codex", "claude-code", "hermes"}


def verify(path: Path) -> dict[str, object]:
    errors: list[str] = []
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            return {"valid": False, "errors": ["manifest must be UTF-8 without BOM"]}
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [str(exc)]}
    if not isinstance(data, dict):
        errors.append("manifest must be an object")
    else:
        errors.extend(f"missing manifest field: {key}" for key in sorted(REQUIRED - set(data)))
        if data.get("manifest_version") != 1:
            errors.append("manifest_version must be 1")
        packages = data.get("host_packages")
        if not isinstance(packages, list):
            errors.append("host_packages must be an array")
        else:
            package_hosts = {item.get("host") for item in packages if isinstance(item, dict)}
            if package_hosts != HOSTS:
                errors.append(f"host_packages must cover exactly {sorted(HOSTS)}")
            for item in packages:
                if not isinstance(item, dict):
                    errors.append("host package entries must be objects")
                    continue
                for field in ("host", "package_revision", "package_digest", "smoke_result"):
                    if field not in item:
                        errors.append(f"host package missing {field}")
                digest = item.get("package_digest")
                if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                    errors.append(f"invalid package digest for {item.get('host')}")
                if item.get("smoke_result") not in {"passed", "failed", "not_run"}:
                    errors.append(f"invalid smoke result for {item.get('host')}")
        if not isinstance(data.get("commands"), list) or not isinstance(data.get("evaluations"), list) or not isinstance(data.get("gates"), list):
            errors.append("commands, evaluations, and gates must be arrays")
        for gate in data.get("gates", []) if isinstance(data.get("gates"), list) else []:
            if not isinstance(gate, dict) or not gate.get("name") or gate.get("status") not in {"passed", "failed", "not_run", "not_applicable"}:
                errors.append("each gate requires name and a registered status")
        if not isinstance(data.get("limitations"), list) or not all(isinstance(item, str) for item in data.get("limitations", [])):
            errors.append("limitations must be a string array")
        if not isinstance(data.get("verifier"), dict) or not data["verifier"].get("identity"):
            errors.append("verifier.identity is required")
    return {"schema": 1, "errors": errors, "valid": not errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = verify(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
