"""Pydantic boundary for new-module schema definitions.

ADR-007 scope: modules added from alpha3 batch 1 onward declare their
payloads here with strict models (extra fields forbidden, mirroring the
legacy whitelist-validation semantics).  Existing modules are not
backfilled; see docs/adr/ADR-007-pydantic-boundary.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for schemas: unknown keys are an error, like the legacy whitelist."""

    model_config = ConfigDict(extra="forbid")
