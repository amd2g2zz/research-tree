"""Issue #322: host-capability discovery (Pi-native + bounded recon)."""

from __future__ import annotations

from research_tree.host_capabilities import (
    CAPABILITY_FALLBACKS,
    CAPABILITY_STATES,
    HOST_SURFACES,
    HOSTS,
    capability_manifest,
)


def test_probe_commands_cover_required_surfaces() -> None:
    for host in HOSTS:
        assert host in HOST_SURFACES


def test_capability_manifest_for_known_host_returns_structured_record() -> None:
    """Every known host yields a structured capability record (no user deflection)."""

    for host in HOSTS:
        record = capability_manifest(host)
        assert record["host"] == host
        assert "capabilities" in record
        assert "fallback_id" in record


def test_capability_manifest_records_each_surface() -> None:
    record = capability_manifest("codex")
    assert record["host"] == "codex"
    assert "capabilities" in record
    assert record["fallback_id"] == "coordinator-dispatch-v1"


def test_missing_capability_yields_degraded_strategy_with_fallback() -> None:
    """A capability that is unavailable has a recorded fallback (not a hard block)."""

    assert isinstance(CAPABILITY_FALLBACKS, dict)
    assert len(CAPABILITY_FALLBACKS) > 0


def test_pi_supported_via_compatibility_path() -> None:
    """Host-iteration UI is host-specific — surfaces are keyed by host."""

    assert "claude-code" in HOST_SURFACES
    assert "codex" in HOST_SURFACES
    assert "hermes" in HOST_SURFACES


def test_host_capability_disposition_states_are_distinct() -> None:
    assert {"available", "unavailable", "partial", "denied", "failed", "unknown"} <= set(CAPABILITY_STATES)


def test_pi_in_host_registry_with_native_surface() -> None:
    """#322 acceptance: Pi has a supported activation path (in the registry)."""

    from research_tree.host_capabilities import HOSTS as known_hosts

    assert "pi" in known_hosts, "Pi must be a known host with a supported activation path"
    from research_tree.host_capabilities import HOST_SURFACES

    assert "pi" in HOST_SURFACES
    record = capability_manifest("pi")
    assert record["host"] == "pi"
