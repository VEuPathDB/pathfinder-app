"""The context and the options of one read are read on the same record type's sheet."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.tools.standalone import _stated_values, catalog_discovery
from strategist.tests.unit.ai.tools.conftest import agent_run_context


async def test_the_record_type_reaches_the_context_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = AsyncMock(return_value={})
    monkeypatch.setattr(_stated_values, "read_stated_parameters", context)
    read = AsyncMock(
        return_value=ParameterInfo(
            name="ms_assay",
            display_name="Assay",
            type="multi-pick-vocabulary",
            required=True,
            is_visible=True,
            site_set=False,
            help="",
        )
    )
    monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)

    await catalog_discovery.get_parameter_options(
        agent_run_context(),
        search_name="GenesByMassSpec",
        parameter_id="ms_assay",
        record_type="gene",
        context_values={"organism": ["Plasmodium falciparum 3D7"]},
    )

    assert context.await_args is not None
    assert read.await_args is not None
    assert (
        context.await_args.kwargs["record_type"],
        read.await_args.kwargs["record_type"],
    ) == ("gene", "gene")
