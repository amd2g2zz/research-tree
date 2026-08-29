"""Pydantic boundary for new-module schema definitions.

ADR-007 scope: modules added from alpha3 batch 1 onward declare their
payloads here with strict models (extra fields forbidden, mirroring the
legacy whitelist-validation semantics).  Existing modules are not
backfilled; see docs/adr/ADR-007-pydantic-boundary.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for schemas: unknown keys are an error, like the legacy whitelist."""

    model_config = ConfigDict(extra="forbid")


class PolicyProposalRef(StrictModel):
    """Lineage reference recorded when an AdaptiveResearchPolicy proposal is consumed."""

    proposal_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    method_boundary: str = Field(min_length=1)
