from __future__ import annotations

import pytest
from veupathdb.domain.parameters import InputStepValue
from veupathdb.wdk import WDKRecordType

from pathfinder.services.experiment import column_tally
from pathfinder.services.experiment.column_tally import (
    ColumnTallyRefusedError,
    run_column_tally,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)


class _Api:
    def __init__(self, record_type: WDKRecordType) -> None:
        self.record_type = record_type

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        del record_type
        return self.record_type


async def test_a_record_type_that_lists_no_counted_column_points_at_a_built_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (_, sequence) = recorded_orthomcl_record_types()
    monkeypatch.setattr(column_tally, "get_strategy_api", lambda _site: _Api(sequence))
    spec = VariantSpec(
        label="Proteins from singleton orthogroups",
        search_name="FromGroups",
        parameters={"group_answer": InputStepValue(step_id="227288990")},
        record_type="sequence",
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_column_tally(
            "orthomcl", spec, "abbreviation", None, record_noun="protein"
        )

    assert str(refused.value) == (
        "protein records cannot be counted by abbreviation here: the site lists no "
        "column they can be counted by outside a step. Build the step and count it "
        "with "
        "count_step_by_column."
    )
