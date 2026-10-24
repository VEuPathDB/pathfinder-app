from __future__ import annotations

import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from pydantic_ai.models import AbstractModel
from pydantic_ai.models.test import TestModel

from pathfinder.ai.tools.standalone.gene_model_investigation import (
    NO_REQUEST_MODEL,
    request_model,
)


class _Spoken(AbstractModel):
    @property
    def model_name(self) -> str:
        return "spoken"

    @property
    def system(self) -> str:
        return "voice"


def test_a_request_model_investigates() -> None:
    model = TestModel()

    assert request_model(model) is model


def test_a_model_that_answers_no_request_is_refused() -> None:
    with pytest.raises(CallRefused) as refused:
        request_model(_Spoken())

    assert str(refused.value) == NO_REQUEST_MODEL
