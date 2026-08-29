from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_tree.schemas import PolicyProposalRef


def test_strict_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PolicyProposalRef.model_validate(
            {"proposal_id": "pp-1", "kind": "method-switch", "method_boundary": "b", "rogue": 1}
        )


def test_policy_proposal_ref_error_names_missing_field() -> None:
    with pytest.raises(ValidationError, match="proposal_id"):
        PolicyProposalRef.model_validate({"kind": "method-switch", "method_boundary": "b"})
