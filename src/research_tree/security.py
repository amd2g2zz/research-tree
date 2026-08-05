"""Permission profiles and redaction at execution/evidence boundaries."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


class SecurityError(ValueError):
    pass


_NETWORK = frozenset({"none", "allowlist", "recorded", "unrestricted"})
_EXECUTION = frozenset({"none", "sandbox", "workspace", "host"})
_SECRET = frozenset({"deny", "redact", "allowlisted"})
_TIERS = frozenset({"read_only", "sandboxed_write", "isolated_execute", "authority_sensitive"})
_SECRET_KEY = re.compile(r"(token|secret|password|credential|authorization|cookie|private[_-]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?:Bearer\s+|sk-|ghp_)[A-Za-z0-9._~+/=-]{8,}", re.I)


def _roots(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(str(value) for value in values)
    if any(not value.strip() for value in result):
        raise SecurityError(f"{label} cannot contain empty paths")
    return result


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    profile_id: str
    read_roots: tuple[str, ...]
    write_roots: tuple[str, ...]
    network: str
    code_execution: str
    secret_policy: str
    timeout_seconds: int
    safety_tier: str

    @classmethod
    def create(cls, *, profile_id: str, read_roots: Iterable[str] = (), write_roots: Iterable[str] = (), network: str = "none", code_execution: str = "none", secret_policy: str = "deny", timeout_seconds: int = 60, safety_tier: str = "read_only") -> "PermissionProfile":
        if not isinstance(profile_id, str) or not re.fullmatch(r"^[a-z][a-z0-9-]{0,63}$", profile_id):
            raise SecurityError("profile_id is invalid")
        if network not in _NETWORK or code_execution not in _EXECUTION or secret_policy not in _SECRET or safety_tier not in _TIERS:
            raise SecurityError("unsupported permission value")
        if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
            raise SecurityError("timeout_seconds must be positive")
        return cls(profile_id, _roots(read_roots, "read_roots"), _roots(write_roots, "write_roots"), network, code_execution, secret_policy, timeout_seconds, safety_tier)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PermissionProfile":
        required = {"profile_id", "read_roots", "write_roots", "network", "code_execution", "secret_policy", "timeout_seconds", "safety_tier"}
        if set(value) != required:
            raise SecurityError("permission profile fields mismatch")
        return cls.create(**dict(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"read_roots": list(self.read_roots), "write_roots": list(self.write_roots)}


def redact(value: Any, *, replacement: str = "[REDACTED]") -> Any:
    """Redact secret-shaped keys and values without retaining raw diagnostics."""
    if isinstance(value, Mapping):
        return {str(key): replacement if _SECRET_KEY.search(str(key)) else redact(child, replacement=replacement) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child, replacement=replacement) for child in value]
    if isinstance(value, tuple):
        return tuple(redact(child, replacement=replacement) for child in value)
    if isinstance(value, str):
        return _SECRET_VALUE.sub(replacement, value)
    return value


def path_within(path: str | Path, roots: Iterable[str | Path]) -> bool:
    candidate = Path(path).resolve(strict=False)
    for root in roots:
        try:
            candidate.relative_to(Path(root).resolve(strict=False))
            return True
        except ValueError:
            continue
    return False
