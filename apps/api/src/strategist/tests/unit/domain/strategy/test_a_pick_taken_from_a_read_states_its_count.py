from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategist.domain.strategy.operational_spec import Measurement


@pytest.mark.parametrize("kind", ["picked_from_a_cut_list", "picked_from_a_lookup"])
def test_a_pick_taken_from_a_read_with_no_count_is_refused(kind: str) -> None:
    with pytest.raises(ValidationError) as refused:
        Measurement.model_validate({"kind": kind, "param": "domain_typeahead"})

    assert "states how many entries the pick took" in str(refused.value)
