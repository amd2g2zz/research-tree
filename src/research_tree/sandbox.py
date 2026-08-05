"""Side-effect-free policy checks used before dispatching an action."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .security import PermissionProfile, SecurityError, path_within


class SandboxViolation(SecurityError):
    def __init__(self, reason: str, *, code: str = "policy_violation") -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True, slots=True)
class SandboxGuard:
    profile: PermissionProfile

    def check_read(self, path: str | Path) -> Path:
        resolved = Path(path).resolve(strict=False)
        if not path_within(resolved, self.profile.read_roots):
            raise SandboxViolation("read path is outside declared roots", code="read_root_denied")
        return resolved

    def check_write(self, path: str | Path) -> Path:
        resolved = Path(path).resolve(strict=False)
        if not path_within(resolved, self.profile.write_roots):
            raise SandboxViolation("write path is outside declared roots", code="write_root_denied")
        if self.profile.safety_tier == "read_only":
            raise SandboxViolation("profile is read-only", code="write_denied")
        return resolved

    def check_executable(self, executable: str) -> str:
        if self.profile.code_execution == "none":
            raise SandboxViolation("code execution is disabled", code="execution_denied")
        if not executable or Path(executable).name != executable:
            raise SandboxViolation("executable must be a declared basename", code="executable_denied")
        return executable

    def check_network(self, endpoint: str, *, allowlist: Iterable[str] = ()) -> str:
        if self.profile.network == "none":
            raise SandboxViolation("network access is disabled", code="network_denied")
        if self.profile.network == "allowlist" and endpoint not in set(allowlist):
            raise SandboxViolation("endpoint is not allowlisted", code="endpoint_denied")
        return endpoint
