"""A card option on a dependent filter is read on its criterion's sheet under the
values that criterion holds."""

from __future__ import annotations

import json

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import ParamFetcher

from strategist.ai.agents.frame_option_checks import hold_an_option_to_its_parameter
from strategist.ai.lead.deltas import FrameResult
from strategist.domain.strategy.card_answers import option_refusal
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.questions import SlotQuestion
from strategist.services.strategies import sheet_params
from strategist.services.strategies.sheet_params import criterion_sheets, read_sheets
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import client_search, suite_search
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_SNPS = suite_search("search_genes_by_ngs_snps")
_UNDER_VIVAX = client_search("search_genes_by_ngs_snps_under_another_organism")
_SEARCH = _SNPS.url_segment
_SAMPLES = "variation_sample_meta"
_PF = "Plasmodium falciparum 3D7"
_VIVAX = "Plasmodium vivax P01"
_PERU = json.dumps(
    {
        "filters": [
            {
                "field": "VAR_36c1c67a",
                "type": "string",
                "isRange": False,
                "includeUnknown": False,
                "value": ["WGS of Patient Isolates from Peru"],
            }
        ]
    }
)
_PUBLISHED = sheet_of(_SNPS.parameters or [])


@pytest.fixture(autouse=True)
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    contexts: list[dict[str, str]] = []

    def _fetch_at(_site_id: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
            contexts.append(context)
            read = (
                _UNDER_VIVAX
                if _VIVAX in context.get("organismSinglePick", "")
                else _SNPS
            )
            return list(read.parameters or [])

        return fetch_at

    monkeypatch.setattr(sheet_params, "wdk_fetch_under_parents_at", _fetch_at)
    return contexts


def _snps(criterion_id: str, organism: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"SNPs in {organism} isolates",
        search_name=_SEARCH,
        record_class="transcript",
        resolved_params={
            "organismSinglePick": BoundValue(
                value=MultiPickValue(values=[organism]), source="stated"
            )
        },
        open_params=[
            OpenSlot(
                criterion_id=criterion_id, param_name=_SAMPLES, param_kind="filter"
            )
        ],
    )


async def test_a_frame_card_offers_a_facet_member_of_the_criterions_organism() -> None:
    ctx = agent_run_context()
    state = ctx.deps.agent_state
    state.operational_spec_draft = OperationalSpec(criteria=[_snps("c_pv", _VIVAX)])
    state.record_read(_SEARCH, _PUBLISHED)
    asked = FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question="Which isolates?",
                dimension=ConstraintKind.UNTYPED,
                recommended_value=_PERU,
                criterion_id="c_pv",
                param_name=_SAMPLES,
                options=[_PERU],
            )
        ],
    )

    assert await hold_an_option_to_its_parameter(ctx, asked) == []


async def test_two_criteria_on_one_search_read_their_own_organisms() -> None:
    spec = OperationalSpec(criteria=[_snps("c_pf", _PF), _snps("c_pv", _VIVAX)])

    sheets = read_sheets(
        await criterion_sheets("plasmodb", spec.criteria, {_SEARCH: _PUBLISHED})
    )
    refusals = {
        criterion_id: option_refusal(
            spec,
            SetValues(criterion_id=criterion_id, params={_SAMPLES: _PERU}),
            sheets=sheets,
            expressions={},
        )
        for criterion_id in ("c_pf", "c_pv")
    }

    assert refusals["c_pv"] is None
    assert refusals["c_pf"] is not None
    assert "has no member WGS of Patient Isolates from Peru" in refusals["c_pf"]


async def test_a_criterion_at_the_published_organism_reads_no_sheet(
    fetched: list[dict[str, str]],
) -> None:
    sheets = await criterion_sheets(
        "plasmodb", [_snps("c_pf", _PF)], {_SEARCH: _PUBLISHED}
    )

    assert (sheets, fetched) == ({"c_pf": _PUBLISHED}, [])


async def test_a_criterion_whose_organism_moved_reads_its_sheet_once(
    fetched: list[dict[str, str]],
) -> None:
    await criterion_sheets("plasmodb", [_snps("c_pv", _VIVAX)], {_SEARCH: _PUBLISHED})

    assert [context["organismSinglePick"] for context in fetched] == [f'["{_VIVAX}"]']
