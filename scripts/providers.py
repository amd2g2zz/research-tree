"""Execution policy for research providers.

Providers are transport choices, not semantic routing.  Every enabled provider
may receive a frame's constraint-compiled query plan; this module only applies
cost, availability, rate-limit, and anti-bot policy.
"""

from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path


CONFIG_NAME = "research_providers.json"
EXECUTABLE_PROVIDERS = frozenset({"anysearch", "openalex", "crossref", "arxiv", "github"})
DEFAULT = {
    "schema": 2,
    "policy": {"allow_paid": False, "allow_high_anti_bot_risk": False,
               "max_parallel": 3, "source_capture_limit_per_frame": 24,
               "on_failure": "record_and_continue"},
    "providers": {
        "anysearch": {"enabled": True, "tier": "free", "anti_bot_risk": "low", "roles": ["discovery", "extract"]},
        "openalex": {"enabled": True, "tier": "free", "anti_bot_risk": "low", "roles": ["discovery", "metadata"]},
        "crossref": {"enabled": True, "tier": "free", "anti_bot_risk": "low", "roles": ["metadata", "verification"]},
        "arxiv": {"enabled": True, "tier": "free", "anti_bot_risk": "low", "roles": ["discovery", "fulltext"]},
        "github": {"enabled": True, "tier": "free", "anti_bot_risk": "low", "roles": ["discovery", "verification"]},
        "ddg": {"enabled": False, "tier": "free", "anti_bot_risk": "medium", "roles": ["fallback"]},
        "brave": {"enabled": False, "tier": "paid", "anti_bot_risk": "low", "roles": ["discovery"]},
        "exa": {"enabled": False, "tier": "paid", "anti_bot_risk": "low", "roles": ["discovery", "extract"]},
    },
}


def workspace() -> Path:
    return Path(os.environ.get("RESEARCH_WORKSPACE", os.getcwd()))


def path() -> Path:
    return workspace() / CONFIG_NAME


def load() -> dict:
    if not path().exists():
        return deepcopy(DEFAULT)
    config = json.loads(path().read_text(encoding="utf-8"))
    if config.get("schema") != 2:
        raise ValueError("unsupported provider configuration")
    return config


def init() -> dict:
    if not path().exists():
        path().write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
    return load()


def eligible() -> dict:
    config = load()
    policy = config["policy"]
    selected, skipped = [], []
    for name, provider in config["providers"].items():
        reasons = []
        if not provider.get("enabled"): reasons.append("disabled")
        if provider.get("tier") == "paid" and not policy.get("allow_paid"): reasons.append("paid_disallowed")
        if provider.get("anti_bot_risk") == "high" and not policy.get("allow_high_anti_bot_risk"): reasons.append("anti_bot_risk_disallowed")
        if name not in EXECUTABLE_PROVIDERS: reasons.append("adapter_unavailable")
        entry = {"provider": name, "roles": provider.get("roles", []), "tier": provider.get("tier")}
        (skipped if reasons else selected).append({**entry, **({"reasons": reasons} if reasons else {})})
    return {"policy": policy, "selected": selected, "skipped": skipped,
            "max_parallel": policy.get("max_parallel", 3)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="providers", description="provider execution policy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init"); sub.add_parser("status"); sub.add_parser("eligible")
    args = parser.parse_args(argv)
    result = init() if args.command == "init" else (eligible() if args.command == "eligible" else load())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
