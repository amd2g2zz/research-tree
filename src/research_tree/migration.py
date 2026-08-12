"""Non-destructive Alpha1 compatibility inventory and release-gated cutover."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


class Alpha1MigrationError(ValueError):
    """Alpha1 state cannot safely participate in an Alpha2 cutover."""


@dataclass(frozen=True)
class Alpha1MigrationItem:
    surface: str
    locator: str
    source_digest: str
    diagnostic_code: str | None
    completion_authority: str = "none"


@dataclass(frozen=True)
class Alpha1MigrationInventory:
    items: tuple[Alpha1MigrationItem, ...]
    fingerprint: str


class Alpha1MigrationService:
    """Read legacy host state while leaving it outside canonical authority."""

    _SURFACES = (
        ("native_checkpoint", ".research-tree-native", "native"),
        ("hermes_checkpoint", ".research-tree-hermes", "hermes"),
    )

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def inventory(self) -> Alpha1MigrationInventory:
        items: list[Alpha1MigrationItem] = []
        for surface, relative_root, expected_host in self._SURFACES:
            root = self.workspace / relative_root
            if not root.is_dir():
                continue
            paths = sorted((*root.rglob("*.json"), *root.rglob("*.jsonl")), key=lambda item: item.as_posix())
            for path in paths:
                if not path.is_file() or path.is_symlink():
                    continue
                raw = path.read_bytes()
                items.append(
                    Alpha1MigrationItem(
                        surface=surface,
                        locator=path.relative_to(self.workspace).as_posix(),
                        source_digest=sha256(raw).hexdigest(),
                        diagnostic_code=self._diagnostic(raw, expected_host),
                    )
                )
        ordered = tuple(sorted(items, key=lambda item: (item.surface, item.locator)))
        fingerprint = sha256(self._canonical_json([asdict(item) for item in ordered])).hexdigest()
        return Alpha1MigrationInventory(items=ordered, fingerprint=fingerprint)

    def write_compatibility_projection(self) -> dict[str, Any]:
        inventory = self.inventory()
        projection = {
            "schema_version": 1,
            "mode": "read_only",
            "completion_authority": "coordinator_only",
            "inventory_fingerprint": inventory.fingerprint,
            "items": [asdict(item) for item in inventory.items],
        }
        target = self.workspace / ".research-tree" / "projections" / "legacy" / "alpha1-state.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._canonical_json(projection) + b"\n")
        return projection

    def migrate(self, *, dry_run: bool = True) -> dict[str, Any]:
        inventory = self.inventory()
        diagnostics = sorted({item.diagnostic_code for item in inventory.items if item.diagnostic_code})
        result = {
            "disposition": "diagnostic_only",
            "completion_authority": "coordinator_only",
            "inventory_fingerprint": inventory.fingerprint,
            "diagnostics": diagnostics,
        }
        if not dry_run:
            self.write_compatibility_projection()
        return result

    def cut_over(self, release_gate: dict[str, Any]) -> dict[str, str]:
        if not isinstance(release_gate, dict) or release_gate.get("registered") is not True:
            raise Alpha1MigrationError("registered release gate is required for cutover")
        if release_gate.get("status") != "pass":
            raise Alpha1MigrationError("release gate must pass before cutover")
        manifest_id = release_gate.get("manifest_id")
        if not isinstance(manifest_id, str) or not manifest_id:
            raise Alpha1MigrationError("passing release gate requires a manifest_id")
        result = {
            "legacy_completion_writes": "retired",
            "completion_authority": "coordinator_only",
            "release_manifest_id": manifest_id,
        }
        target = self.workspace / ".research-tree" / "migration-cutover.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._canonical_json({"schema_version": 1, **result}) + b"\n")
        return result

    def rollback(self) -> dict[str, str]:
        """Disable the Alpha2 cutover marker without touching legacy sources."""

        marker = self.workspace / ".research-tree" / "migration-cutover.json"
        marker.unlink(missing_ok=True)
        return {"cutover": "disabled", "legacy_material": "retained_read_only"}

    @staticmethod
    def _diagnostic(raw: bytes, expected_host: str) -> str | None:
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "partial_or_corrupt_store"
        if not isinstance(value, dict):
            return "partial_or_corrupt_store"
        if "schema_version" in value and value["schema_version"] != 1:
            return "unsupported_schema_version"
        if "host" in value and value["host"] != expected_host:
            return "stale_host_package_state"
        duplicates = value.get("duplicate_artifacts")
        if isinstance(duplicates, list) and len(duplicates) != len(set(map(str, duplicates))):
            return "duplicate_artifacts"
        return None

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
