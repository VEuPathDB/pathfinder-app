"""A slot card keeps every offered value the site's vocabulary holds, wherever
the vocabulary lists it, on the recorded organism sheets."""

from __future__ import annotations

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamIntent,
    format_param_info_typed,
    resolve_params_with_intent,
)

from pathfinder.ai.tools.standalone._frame_sources import open_slots
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import SetValues, SlotQuestion

_PLASMODB = [
    "Plasmodium falciparum 3D7",
    "Plasmodium adleri G01",
    "Plasmodium berghei ANKA",
    "Plasmodium billcollinsi G01",
    "Plasmodium blacklocki G01",
    "Plasmodium brasilianum strain Bolivian I",
    "Plasmodium chabaudi chabaudi CB",
    "Plasmodium coatneyi",
]
_MOSQUITOES = [
    "Anopheles gambiae PEST",
    "Anopheles coluzzii Ngousso",
    "Anopheles stephensi Indian",
    "Anopheles funestus FUMOZ",
    "Anopheles darlingi Coari",
    "Aedes aegypti LVP_AGWG",
    "Aedes albopictus Foshan",
    "Culex quinquefasciatus JHB 2020",
]


def _sheet(name: str) -> list[ParameterInfo]:
    body = load_recorded(name).json_body()
    return format_param_info_typed(
        WDKSearchResponse.model_validate(body).search_data.parameters or []
    )


def _vectorbase_exon_count_sheet() -> list[ParameterInfo]:
    """The exon-count sheet over the VectorBase organism vocabulary."""
    vectorbase = next(
        info
        for info in _sheet("search_genes_by_gene_model_chars")
        if info.name == "organism_select_none"
    )
    return [
        info.model_copy(update={"vocab_leaves": vectorbase.vocabulary()})
        if info.name == "organism"
        else info
        for info in _sheet("search_genes_by_exon_count")
    ]


async def _criterion(infos: list[ParameterInfo], text: str) -> Criterion:
    async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
        del context
        return infos

    resolved = await resolve_params_with_intent(
        fetch_at=fetch_at, intent=ParamIntent(text=text)
    )
    return Criterion(
        id="c1",
        text=text,
        search_name="GenesByExonCount",
        open_params=open_slots("c1", resolved.open_slots, infos),
    )


def _offered(criterion: Criterion, values: list[str]) -> list[str]:
    card = SlotQuestion(
        question="Which organism?",
        criterion_id="c1",
        param_name="organism",
        options=values,
    ).typed(criterion, noun="gene")
    offered: list[str] = []
    for option in card.options:
        match option.binding:
            case SetValues(params={"organism": value}):
                offered.append(value)
            case _:
                pass
    return offered


async def test_falciparum_3d7_past_the_twentieth_organism_is_offered() -> None:
    criterion = await _criterion(
        _sheet("search_genes_by_exon_count"), "multi-exon malaria parasite genes"
    )

    assert criterion.open_params[0].options.index("Plasmodium falciparum 3D7") == 25
    assert _offered(criterion, _PLASMODB) == _PLASMODB


async def test_mosquitoes_after_the_ticks_are_offered() -> None:
    criterion = await _criterion(
        _vectorbase_exon_count_sheet(), "multi-exon mosquito genes"
    )

    assert criterion.open_params[0].options[:3] == [
        "Arthropoda",
        "Arachnida",
        "Ixodida",
    ]
    assert _offered(criterion, _MOSQUITOES) == _MOSQUITOES
