import hashlib

import pytest

from research_tree import (
    AcquisitionError, MethodError, MethodRegistry, MethodSpec, PermissionProfile,
    SandboxGuard, SandboxViolation, authorize_acquisition, record_failure, redact,
)


def test_permission_profile_redacts_and_enforces_paths(tmp_path):
    profile = PermissionProfile.create(profile_id="read-only", read_roots=[str(tmp_path)], safety_tier="read_only")
    guard = SandboxGuard(profile)
    assert guard.check_read(tmp_path / "input.bin") == (tmp_path / "input.bin").resolve()
    with pytest.raises(SandboxViolation):
        guard.check_read(tmp_path.parent / "outside")
    with pytest.raises(SandboxViolation):
        guard.check_write(tmp_path / "out.json")
    assert redact({"token": "Bearer abcdefghijkl", "message": "safe"})["token"] == "[REDACTED]"


def test_method_registry_switch_is_deterministic():
    registry = MethodRegistry([
        MethodSpec("web-search", "web", ("documentation",), "public", 30),
        MethodSpec("local-reference", "file", ("documentation",), "local", 10),
    ])
    assert registry.switch("web-search", "documentation").method_id == "local-reference"
    with pytest.raises(MethodError):
        registry.switch("local-reference", "image")


def test_failed_acquisition_is_not_silent_and_network_is_authorized():
    profile = PermissionProfile.create(profile_id="public", network="allowlist")
    authorize_acquisition(profile, needs_network=True)
    result = record_failure(acquisition_id="acq-1", method_id="web-search", locator="https://example.invalid", reason="blocked URL", provenance_group="url:example.invalid", next_action="method-switch")
    assert result.status == "failed"
    assert result.next_action == "method-switch"
    with pytest.raises(AcquisitionError):
        authorize_acquisition(PermissionProfile.create(profile_id="local"), needs_network=True)
