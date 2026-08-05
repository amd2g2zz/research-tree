"""Shared Draft 2020-12 contract validation for runtime and host adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


class ContractRegistryError(ValueError):
    pass


class ContractRegistry:
    def __init__(self, schema_root: str | Path) -> None:
        self.schema_root = Path(schema_root).resolve()
        if not self.schema_root.is_dir():
            raise ContractRegistryError(f"schema root does not exist: {self.schema_root}")
        self._validators: dict[str, Draft202012Validator] = {}

    @classmethod
    def from_repository(cls, root: str | Path) -> "ContractRegistry":
        return cls(
            Path(root)
            / "openspec"
            / "changes"
            / "unify-research-runtime-alpha2"
            / "schemas"
        )

    def schema_names(self) -> tuple[str, ...]:
        return tuple(path.name for path in sorted(self.schema_root.glob("*.json")))

    def validator(self, schema_name: str) -> Draft202012Validator:
        cached = self._validators.get(schema_name)
        if cached is not None:
            return cached
        path = (self.schema_root / schema_name).resolve()
        if path.parent != self.schema_root or not path.is_file():
            raise ContractRegistryError(f"schema does not exist: {schema_name}")
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ContractRegistryError(f"{schema_name}: UTF-8 BOM")
        try:
            schema = json.loads(raw.decode("utf-8"))
            Draft202012Validator.check_schema(schema)
        except (UnicodeDecodeError, json.JSONDecodeError, SchemaError) as error:
            raise ContractRegistryError(f"{schema_name}: {error}") from error
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self._validators[schema_name] = validator
        return validator

    def validate(self, schema_name: str, instance: Any) -> None:
        try:
            self.validator(schema_name).validate(instance)
        except ValidationError as error:
            location = ".".join(str(item) for item in error.absolute_path) or "<root>"
            raise ContractRegistryError(
                f"{schema_name}:{location}: {error.message}"
            ) from error

    def validate_examples(self) -> dict[str, int]:
        index_path = self.schema_root / "examples" / "index-v1.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContractRegistryError(f"example index: {error}") from error
        cases = index.get("entries")
        if not isinstance(cases, list):
            raise ContractRegistryError("example index cases must be an array")
        valid_count = 0
        invalid_count = 0
        for case in cases:
            if (
                not isinstance(case, dict)
                or not {"schema", "valid", "invalid"} <= set(case)
                or set(case) - {"schema", "valid", "p0", "invalid"}
            ):
                raise ContractRegistryError("example case fields mismatch")
            self.validate(case["schema"], case["valid"])
            valid_count += 1
            try:
                self.validate(case["schema"], case["invalid"])
            except ContractRegistryError:
                invalid_count += 1
            else:
                raise ContractRegistryError(
                    f"{case['schema']}: registered invalid example passed validation"
                )
        return {"valid_examples": valid_count, "invalid_examples": invalid_count}
