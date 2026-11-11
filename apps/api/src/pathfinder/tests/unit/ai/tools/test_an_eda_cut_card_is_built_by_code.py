from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaDistributionResponse,
    EdaFilter,
    EdaNumberRangeFilter,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaSubsetDescriptor,
)

from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.recorded_cards import the_card_asked
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import _eda_step_guard
from pathfinder.ai.tools.standalone._eda_step_guard import the_subset_basis
from pathfinder.domain.strategy.analysis_binding import SubsetBasis
from pathfinder.domain.strategy.question_options import TailRule
from pathfinder.services.eda import cut_offer
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    permission_entry,
    study_of,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_ENTITY

_ESSENTIAL = "apicomplexan genes that are essential in any experiment"
_LYTIC = "DS_lytic"
_BLOOD = "DS_blood"
_SCORE = "VAR_score"
_FITNESS = "VAR_fitness"
_PHENOTYPE = "VAR_phenotype"
_GENE = {
    "id": "VEUPATHDB_GENE_ID",
    "type": "string",
    "displayName": "Gene",
    "dataShape": "categorical",
}

_LOW_5 = "Lowest 6.5% of Mean Phenotype Score: at most -3 (65 genes)"
_OFFERED = [
    _LOW_5,
    "Lowest 10.0% of Mean Phenotype Score: at most -2 (100 genes)",
    "Highest 5.0% of Mean Phenotype Score: at least 1 (50 genes)",
    "Highest 20.0% of Mean Phenotype Score: at least 0 (200 genes)",
    "Phenotype: Essential (120 genes)",
    "Phenotype: Dispensable (880 genes)",
]


def _continuous(variable_id: str, name: str) -> dict[str, Any]:
    return {
        "id": variable_id,
        "type": "number",
        "displayName": name,
        "dataShape": "continuous",
        "distributionDefaults": {"rangeMin": -7, "rangeMax": 7, "binWidth": 1},
    }


def _lytic() -> EdaStudyDetail:
    phenotype = {
        "id": _PHENOTYPE,
        "type": "string",
        "displayName": "Phenotype",
        "dataShape": "categorical",
        "vocabulary": ["Dispensable", "Essential"],
    }
    variables = [_GENE, _continuous(_SCORE, "Mean Phenotype Score"), phenotype]
    return study_of(variables, entity_id=PHENOTYPE_ENTITY)


def _blood() -> EdaStudyDetail:
    return study_of(
        [_GENE, _continuous(_FITNESS, "Relative Growth Rate")],
        entity_id=PHENOTYPE_ENTITY,
    )


def _numeric(start: int, counts: Sequence[int]) -> EdaDistributionResponse:
    return EdaDistributionResponse.model_validate(
        {
            "histogram": [
                {
                    "value": count,
                    "binStart": f"{start + i:.1f}",
                    "binEnd": f"{start + i + 1:.1f}",
                    "binLabel": f"[{start + i:.1f},{start + i + 1:.1f})",
                }
                for i, count in enumerate(counts)
            ]
        }
    )


def _classes(counts: dict[str, int]) -> EdaDistributionResponse:
    return EdaDistributionResponse.model_validate(
        {
            "histogram": [
                {"value": n, "binStart": v, "binEnd": v, "binLabel": v}
                for v, n in counts.items()
            ]
        }
    )


_DISTRIBUTIONS = {
    (_LYTIC, _SCORE): _numeric(-7, [5, 10, 20, 30, 35, 400, 300, 150, 50, 0]),
    (_LYTIC, _PHENOTYPE): _classes({"Essential": 120, "Dispensable": 880}),
    (_BLOOD, _FITNESS): _numeric(-6, [3, 4, 5, 8, 30, 30, 8, 5, 4, 3]),
}


async def _study(
    _site: str, dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    return permission_entry(), _lytic() if dataset_id == _LYTIC else _blood()


async def _preview(
    _site: str,
    *,
    dataset_id: str,
    entity_id: str,
    filters: Sequence[EdaFilter],
    distribution_variable_id: str | None = None,
) -> SubsetPreview:
    if filters:
        return SubsetPreview(
            entity_id=entity_id,
            entity_display_name=entity_id,
            entity_display_name_plural=entity_id,
            count=sum(_inside(dataset_id, f) for f in filters),
            unfiltered_count=1000,
            distribution=None,
        )
    return SubsetPreview(
        entity_id=entity_id,
        entity_display_name=entity_id,
        entity_display_name_plural=entity_id,
        count=1000,
        unfiltered_count=1000,
        distribution=_DISTRIBUTIONS[(dataset_id, distribution_variable_id or "")],
    )


def _inside(dataset_id: str, each: EdaFilter) -> int:
    match each:
        case EdaNumberRangeFilter(variable_id=variable_id, min=low, max=high):
            bins = _DISTRIBUTIONS[(dataset_id, variable_id)].histogram
            return int(
                sum(
                    b.value
                    for b in bins
                    if float(b.bin_start) >= low and float(b.bin_end) <= high
                )
            )
        case _:
            raise AssertionError(each)


@pytest.fixture(autouse=True)
def _wired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_eda_step_guard, "get_study_detail_for_dataset", _study)
    monkeypatch.setattr(cut_offer, "preview_subset", _preview)


def _at_most(dataset_id: str, variable_id: str, cut: float) -> EdaAnalysisDetail:
    filters: list[EdaFilter] = [
        EdaNumberRangeFilter(
            entity_id=PHENOTYPE_ENTITY, variable_id=variable_id, min=-7, max=cut
        )
    ]
    return _analysis_of(filters, dataset_id=dataset_id)


def _analysis_of(
    filters: list[EdaFilter], *, dataset_id: str = _LYTIC
) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="essential genes",
        study_id=dataset_id,
        num_filters=len(filters),
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=filters)
        ),
    )


async def _basis(
    ctx: RunContext[LeadDeps], analysis: EdaAnalysisDetail
) -> list[SubsetBasis]:
    state = ctx.deps.state
    return await the_subset_basis(
        "plasmodb",
        analysis.study_id,
        analysis,
        said=[_ESSENTIAL],
        thread=state.domain,
    )


async def _pick_the_low_tail(ctx: RunContext[LeadDeps]) -> None:
    state = ctx.deps.state
    with pytest.raises(ModelRetry):
        await _basis(ctx, _at_most(_LYTIC, _SCORE, -3))
    [card] = the_card_asked([], state.domain.open_questions)
    answer = UserQuestionAnswer(
        question_id=card.id, prompt=card.prompt, chosen_labels=[_LOW_5]
    )
    apply_option_bindings(state, [answer], [card], sheets={})


async def test_the_refused_cut_records_a_card_of_code_built_cuts(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry) as refusal:
        await _basis(lead_ctx, _at_most(_LYTIC, _SCORE, -3))

    [card] = the_card_asked([], lead_ctx.deps.state.domain.open_questions)
    assert [o.label for o in card.options] == _OFFERED
    assert "consult_user" in str(refusal.value)
    assert "Nothing was written" in str(refusal.value)


async def test_the_card_replaces_a_question_the_model_writes_on_its_prompt(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry):
        await _basis(lead_ctx, _at_most(_LYTIC, _SCORE, -3))
    recorded = lead_ctx.deps.state.domain.open_questions
    [held] = the_card_asked([], recorded)
    written = held.model_copy(
        update={
            "options": [
                o.model_copy(update={"label": "Use the strongest tail"})
                for o in held.options[:2]
            ]
        }
    )

    [card] = the_card_asked([written], recorded)
    assert [o.label for o in card.options] == _OFFERED


async def test_a_picked_tail_label_binds_its_bound(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    await _pick_the_low_tail(lead_ctx)

    assert lead_ctx.deps.state.domain.tail_rules == {
        _LOW_5: TailRule(end="low", percent=5)
    }
    assert await _basis(lead_ctx, _at_most(_LYTIC, _SCORE, -3)) == [
        SubsetBasis(
            filter="Mean Phenotype Score is between -7.0 and -3.0",
            basis="card",
            picked=_LOW_5,
        )
    ]


async def test_a_picked_rule_accepts_another_studys_own_edge(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    await _pick_the_low_tail(lead_ctx)
    asked = list(lead_ctx.deps.state.domain.open_questions)

    assert await _basis(lead_ctx, _at_most(_BLOOD, _FITNESS, -4)) == [
        SubsetBasis(
            filter="Relative Growth Rate is between -7.0 and -4.0",
            basis="card",
            picked=_LOW_5,
        )
    ]
    assert lead_ctx.deps.state.domain.open_questions == asked


async def test_a_picked_rule_refuses_another_bound_and_names_the_studys_edge(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    await _pick_the_low_tail(lead_ctx)
    asked = list(lead_ctx.deps.state.domain.open_questions)

    with pytest.raises(ModelRetry) as refusal:
        await _basis(lead_ctx, _at_most(_BLOOD, _FITNESS, -1))

    message = str(refusal.value)
    assert "at most -4 (7 genes)" in message
    assert "max=-4" in message
    assert lead_ctx.deps.state.domain.open_questions == asked


async def test_a_picked_class_binds_as_the_studys_own_class_and_holds_no_rule(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    state = lead_ctx.deps.state
    with pytest.raises(ModelRetry):
        await _basis(lead_ctx, _at_most(_LYTIC, _SCORE, -3))
    [card] = the_card_asked([], state.domain.open_questions)
    picked = "Phenotype: Essential (120 genes)"
    answer = UserQuestionAnswer(
        question_id=card.id, prompt=card.prompt, chosen_labels=[picked]
    )
    apply_option_bindings(state, [answer], [card], sheets={})
    essential = EdaStringSetFilter(
        entity_id=PHENOTYPE_ENTITY, variable_id=_PHENOTYPE, string_set=["Essential"]
    )

    assert (state.domain.card_picks, state.domain.tail_rules) == ([picked], {})
    assert await _basis(lead_ctx, _analysis_of([essential])) == [
        SubsetBasis(filter="Phenotype is one of Essential", basis="study")
    ]
