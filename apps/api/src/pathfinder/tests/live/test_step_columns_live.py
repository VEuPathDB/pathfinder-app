"""A search step's columns, read live over the whole step, fit the values the step
was built with, and the count of each read is the step's own count."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.wdk import NewStepSpec, WDKSearchConfig, WDKStepTree, get_strategy_api
from veupathdb_mcp.catalog import read_search_definition

from pathfinder.ai.tools.standalone._step_columns import column_bounds, settled
from pathfinder.ai.tools.standalone.results import read_column_fit
from pathfinder.domain.evidence import ColumnFit
from pathfinder.domain.strategy.operational_spec import Criterion, bind_values

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_PERCENTILE = "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
_TM: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
    "min_tm": StringValue(value="2"),
    "max_tm": StringValue(value="99"),
}
_EXPRESSED: dict[str, ParamValue] = {
    "profileset_generic": StringValue(
        value=(
            "Asexual blood stages and salivary gland sporozoite and midgut "
            "oocyst transcriptomes - Sense"
        )
    ),
    "samples_percentile_generic": MultiPickValue(
        values=["asexual blood stages", "midgut oocysts"]
    ),
    "min_expression_percentile": StringValue(value="80"),
    "max_expression_percentile": StringValue(value="100"),
    "any_or_all": StringValue(value="any"),
    "protein_coding_only": StringValue(value="yes"),
    "channel": StringValue(value="Channel 1"),
}

Built = Callable[[str, dict[str, ParamValue]], Awaitable[tuple[int, int]]]


@pytest.fixture
async def built(wdk_identity: str) -> AsyncGenerator[Built]:
    """Build one search step inside a strategy, and delete both at the end."""
    del wdk_identity
    api = get_strategy_api(_SITE)
    made: list[int] = []

    async def build(search: str, params: dict[str, ParamValue]) -> tuple[int, int]:
        step = await api.create_step(
            NewStepSpec(
                search_name=search,
                search_config=WDKSearchConfig(
                    parameters={name: v.to_wire() for name, v in params.items()}
                ),
            ),
            record_type="transcript",
        )
        strategy = await api.create_strategy(
            WDKStepTree(step_id=step.id), name="pathfinder-live-lane", is_internal=True
        )
        made.append(strategy.id)
        return step.id, await api.get_step_count(step.id)

    try:
        yield build
    finally:
        for strategy_id in made:
            with contextlib.suppress(Exception):
                await api.delete_strategy(strategy_id)


async def _fits(
    search: str, params: dict[str, ParamValue], step_id: int
) -> list[ColumnFit]:
    catalog = await get_strategy_api(_SITE).get_record_type_info("transcript")
    searches = catalog.searches or []
    definition = next(s for s in searches if s.url_segment == search)
    criterion = Criterion(
        id="c_live",
        text="the step's own values",
        search_name=search,
        resolved_params=bind_values(params, "stated"),
    )
    parameters = (await read_search_definition(_SITE, "transcript", search)).parameters
    bounds = column_bounds(
        definition, parameters or [], catalog.attributes or [], searches, params.get
    )
    read = [await read_column_fit(_SITE, step_id, criterion, b) for b in bounds]
    return settled(list(zip(bounds, read, strict=True)))


async def test_every_gene_of_a_transmembrane_step_fits_its_tm_count(
    built: Built,
) -> None:
    step_id, count = await built("GenesByTransmembraneDomains", _TM)

    fits = await _fits("GenesByTransmembraneDomains", _TM, step_id)

    assert [(f.column, f.bound_value, f.fits, f.fitting, f.total) for f in fits] == [
        ("tm_count", "2 to 99", "all", count, count)
    ]


async def test_a_percentile_step_reads_its_own_columns_from_their_histograms(
    built: Built,
) -> None:
    step_id, _count = await built(_PERCENTILE, _EXPRESSED)

    fits = await _fits(_PERCENTILE, _EXPRESSED, step_id)

    assert [(f.column, f.counted_in, f.bound_value, f.fits) for f in fits] == [
        ("min_percentile_chosen", "transcripts", "80 to 100", "all"),
        ("max_percentile_chosen", "transcripts", "80 to 100", "all"),
    ]
