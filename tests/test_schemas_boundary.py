from __future__ import annotations

import pytest
from pydantic import BaseModel

from research_tree.schemas import StrictModel


class _Sample(StrictModel):
    proposal_id: str


def test_strict_model_subclass_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="extra_forbidden|rogue"):
        _Sample.model_validate({"proposal_id": "pp-1", "rogue": 1})


def test_strict_model_error_names_missing_field() -> None:
    with pytest.raises(ValueError, match="proposal_id"):
        _Sample.model_validate({})


def test_strict_model_is_pydantic_base() -> None:
    assert issubclass(StrictModel, BaseModel)
