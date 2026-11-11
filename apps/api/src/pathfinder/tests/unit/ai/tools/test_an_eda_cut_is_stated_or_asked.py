from __future__ import annotations

from typing import Any

import pytest
from assistant_core.graph.turn_state import ConsultOption, UserQuestionAnswer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaFilter,
    EdaNumberRangeFilter,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaSubsetDescriptor,
)

from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.ai.tools.standalone._eda_step_guard import subset_basis
from pathfinder.domain.strategy.analysis_binding import SubsetBasis
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    permission_entry,
    study_of,
)
from pathfinder.tests._support.eda_step_doubles import (
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET, PHENOTYPE_ENTITY
from pathfinder.tests._support.run_context import lead_run_context

_ESSENTIAL_ANYWHERE = (
    "I want a list of apicomplexan genes that are essential in any experiment "
    "from any apicomplexan organism"
)
_MUTABILITY = "VAR_47355ec9"
_MIS_PLUS_RANK = "VAR_a16860c0"
_PHENOTYPE = "VAR_9febbd7f"
_SCORE = "VAR_score"
_PICK = "Mean Phenotype Score at most -2"


def _a1h1() -> EdaStudyDetail:
    variables: list[dict[str, Any]] = [
        {
            "id": _MUTABILITY,
            "type": "string",
            "displayName": "Mutability in CDS",
            "dataShape": "categorical",
            "vocabulary": ["mutable", "nonmutable", "not determined"],
        },
        {
            "id": _MIS_PLUS_RANK,
            "type": "integer",
            "displayName": "MIS Plus Rank",
            "dataShape": "continuous",
            "definition": "Rank of MIS Plus",
            "distributionDefaults": {"rangeMin": 1, "rangeMax": 5408},
        },
    ]
    return study_of(variables, entity_id=PHENOTYPE_ENTITY)


def _berghei() -> EdaStudyDetail:
    variables: list[dict[str, Any]] = [
        {
            "id": _PHENOTYPE,
            "type": "string",
            "displayName": "Phenotype",
            "dataShape": "categorical",
            "vocabulary": [
                "Dispensable",
                "Essential",
                "Fast",
                "Insufficient data",
                "Slow",
            ],
        },
    ]
    return study_of(variables, entity_id=PHENOTYPE_ENTITY)


def _lytic() -> EdaStudyDetail:
    variables: list[dict[str, Any]] = [
        {
            "id": _SCORE,
            "type": "number",
            "displayName": "Mean Phenotype Score",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": -6.89, "rangeMax": 2.96},
        },
    ]
    return study_of(variables, entity_id=PHENOTYPE_ENTITY)


def _rank_top_100() -> EdaNumberRangeFilter:
    return EdaNumberRangeFilter(
        entity_id=PHENOTYPE_ENTITY, variable_id=_MIS_PLUS_RANK, min=1, max=100
    )


def _score_at_most(cut: float) -> EdaNumberRangeFilter:
    return EdaNumberRangeFilter(
        entity_id=PHENOTYPE_ENTITY, variable_id=_SCORE, min=-6.89, max=cut
    )


def test_an_unstated_rank_cut_is_refused_with_the_studys_classes() -> None:
    with pytest.raises(ModelRetry) as refusal:
        subset_basis([_rank_top_100()], _a1h1(), said=[_ESSENTIAL_ANYWHERE], picks=[])

    message = str(refusal.value)
    assert "MIS Plus Rank is between 1.0 and 100.0" in message
    assert "consult_user" in message
    assert "Mutability in CDS: mutable, nonmutable, not determined" in message
    assert "1 to 5408" in message
    assert "Nothing was written" in message


def test_a_class_the_study_declares_passes() -> None:
    essential = EdaStringSetFilter(
        entity_id=PHENOTYPE_ENTITY, variable_id=_PHENOTYPE, string_set=["Essential"]
    )

    assert subset_basis(
        [essential], _berghei(), said=[_ESSENTIAL_ANYWHERE], picks=[]
    ) == [SubsetBasis(filter="Phenotype is one of Essential", basis="study")]


def test_a_cut_the_researcher_wrote_passes() -> None:
    assert subset_basis(
        [_score_at_most(-1)],
        _lytic(),
        said=["Toxoplasma genes with a fitness below -1 in the lytic screen"],
        picks=[],
    ) == [
        SubsetBasis(
            filter="Mean Phenotype Score is between -6.89 and -1.0", basis="stated"
        )
    ]


@pytest.mark.parametrize(
    "said",
    ["Toxoplasma genes with a fitness below 1", "a fitness score from -6 - 1"],
)
def test_a_cut_written_without_its_minus_is_refused(said: str) -> None:
    with pytest.raises(ModelRetry):
        subset_basis([_score_at_most(-1)], _lytic(), said=[said], picks=[])


def test_a_rank_span_written_with_a_dash_states_its_end() -> None:
    assert subset_basis(
        [_rank_top_100()], _a1h1(), said=["the genes ranked 1-100"], picks=[]
    ) == [SubsetBasis(filter="MIS Plus Rank is between 1.0 and 100.0", basis="stated")]


def test_a_cut_picked_on_a_card_passes(lead_ctx: RunContext[LeadDeps]) -> None:
    state = lead_ctx.deps.state
    prompt = "Which fitness cut reads as essential in the lytic screen?"
    asked = CardQuestion(
        id="own-1",
        prompt=prompt,
        options=[
            ConsultOption(label=_PICK),
            ConsultOption(label="Mean Phenotype Score at most -4"),
        ],
    )
    answer = UserQuestionAnswer(
        question_id="own-1", prompt=prompt, chosen_labels=[_PICK]
    )
    with pytest.raises(ModelRetry):
        subset_basis(
            [_score_at_most(-2)],
            _lytic(),
            said=state.researcher_messages(),
            picks=state.domain.card_picks,
        )

    apply_option_bindings(state, [answer], [asked], sheets={})

    assert state.domain.card_picks == [_PICK]
    assert subset_basis(
        [_score_at_most(-2)],
        _lytic(),
        said=state.researcher_messages(),
        picks=state.domain.card_picks,
    ) == [
        SubsetBasis(
            filter="Mean Phenotype Score is between -6.89 and -2.0",
            basis="card",
            picked=_PICK,
        )
    ]


async def _a1h1_reader(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    return permission_entry(), _a1h1()


async def _no_commit(**kwargs: object) -> CommitResult:
    reason = f"no export may reach the commit: {sorted(kwargs)}"
    raise AssertionError(reason)


def _analysis(filters: list[EdaFilter]) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="A1H1 essential genes",
        study_id=PHENOTYPE_DATASET,
        num_filters=len(filters),
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=filters)
        ),
    )


async def test_create_eda_step_writes_no_unstated_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Essential genes", "plasmodb"))
    ctx = lead_run_context(user_prompt=_ESSENTIAL_ANYWHERE, strategy_session=session)
    wire_analysis(monkeypatch, eda_step, _analysis([_rank_top_100()]))
    counted = wire_gene_count(monkeypatch, study=_a1h1_reader)
    monkeypatch.setattr(eda_step, "apply_operations_and_commit", _no_commit)

    with pytest.raises(ModelRetry) as refusal:
        await eda_step.create_eda_step(ctx)

    assert "consult_user" in str(refusal.value)
    graph = session.get_graph(None)
    assert graph is not None
    assert list(graph.steps) == []
    assert counted == []
