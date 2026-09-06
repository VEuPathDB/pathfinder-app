from __future__ import annotations

import pytest
from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.errors import WDKError
from veupathdb_mcp.controls.control_tests import (
    IntersectionConfig,
    run_positive_negative_controls,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_ORG = "Plasmodium falciparum 3D7"


async def test_control_test_bad_target_surfaces_error(
    wdk_session: None,
) -> None:
    del wdk_session
    config = IntersectionConfig(
        site_id="plasmodb",
        record_type="transcript",
        target_search_name="GenesByText",
        target_parameters={
            "text_expression": StringValue(value="kinase"),
            "text_fields": MultiPickValue(values=["not_a_real_field"]),
            "document_type": StringValue(value="gene"),
            "text_search_organism": MultiPickValue(values=[_ORG]),
        },
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
    )
    with pytest.raises(WDKError) as refusal:
        await run_positive_negative_controls(
            config, positive_controls=["PF3D7_0100100"]
        )
    assert refusal.value.status == 422
    assert "not_a_real_field" in str(refusal.value)
