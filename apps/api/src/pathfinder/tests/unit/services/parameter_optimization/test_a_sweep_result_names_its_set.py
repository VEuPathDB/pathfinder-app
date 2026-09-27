"""A sweep result names the saved control set every setting was scored on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.services.parameter_optimization.config import SweepResult

_TRIAL = {"variantId": "v0", "status": "success", "score": 0.5}


def test_a_sweep_result_without_its_set_is_refused() -> None:
    with pytest.raises(ValidationError, match="controlSet"):
        SweepResult.model_validate(
            {
                "variants": [_TRIAL],
                "best": None,
                "searchName": "GenesByExonCount",
                "objective": "f1",
            }
        )


def test_a_sweep_result_carries_the_set_it_scored() -> None:
    sweep = SweepResult.model_validate(
        {
            "variants": [_TRIAL],
            "best": None,
            "searchName": "GenesByExonCount",
            "objective": "f1",
            "controlSet": {
                "id": "5f1c6a2e-0000-4000-8000-00000000c0de",
                "name": "Kinases",
            },
        }
    )

    assert sweep.control_set.name == "Kinases"
    assert sweep.best is not None
    assert sweep.best.variant_id == "v0"
