"""A slot card keeps every offered value the site's vocabulary holds, wherever
the vocabulary lists it, on the recorded organism sheets."""

from __future__ import annotations

from veupathdb.wdk import WDKParameter, WDKSearchResponse
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamIntent,
    resolve_params_with_intent,
)

from strategist.ai.tools.standalone._frame_sources import open_slots
from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.questions import SlotQuestion
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.qa_recording import client_recording
from strategist.tests._support.sheets import declarations

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
    body = client_recording(name).json_body()
    return sheet_of(WDKSearchResponse.model_validate(body).search_data.parameters or [])


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
    async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
        del context
        return declarations(infos)

    resolved = await resolve_params_with_intent(
        about=None,
        fetch_at=fetch_at,
        filter_reads=NoFilterReads(),
        intent=ParamIntent(text=text),
        search_name="GenesByExonCount",
        stated={},
    )
    return Criterion(
        id="c1",
        text=text,
        search_name="GenesByExonCount",
        open_params=open_slots("c1", resolved.open_slots, infos, frozenset()),
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
