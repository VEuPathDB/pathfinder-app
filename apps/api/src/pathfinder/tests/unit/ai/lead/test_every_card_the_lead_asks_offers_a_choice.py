"""Every card the Lead asks offers a choice: a question card with one option is
refused where it is built, and a requirement FRAME names as unstated is asked
as its own drop-or-keep question, so a free-text card about it is refused."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.guarantees import registered_tools
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.lead_consult import refuse_a_card_that_binds_nothing
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.questions import Keep, SlotQuestion, Withdraw
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_BRL01_CARD = {
    "id": "q1",
    "kind": "single_choice",
    "prompt": (
        "The site has no BRL01 spore-expression search to bind. Should the "
        "strategy remain limited to BRL01 genes with a predicted signal peptide, "
        "without an expression constraint?"
    ),
    "options": [
        {
            "label": "Keep only the BRL01 predicted signal-peptide search",
            "recommended": True,
        }
    ],
    "dimension": "data_type",
}
_FUNGIDB_CARD = {
    "id": "q1",
    "kind": "single_choice",
    "prompt": (
        "The existing differential-expression step is bound with an effect-size "
        "cutoff of 1.0. Should it be recreated as the same comparison with an "
        "absolute effect-size cutoff of 1.5 so the gene count can be compared?"
    ),
    "options": [{"label": "1.5", "recommended": True}],
    "dimension": "statistical_threshold",
}


@pytest.mark.parametrize(
    ("card", "label"),
    [
        (_BRL01_CARD, "Keep only the BRL01 predicted signal-peptide search"),
        (_FUNGIDB_CARD, "1.5"),
    ],
)
def test_a_card_with_one_option_is_refused_where_it_is_built(
    card: dict[str, Any], label: str
) -> None:
    with pytest.raises(ValidationError) as refused:
        CardQuestion.model_validate(card)

    assert f"offers 1 option [{label!r}], which is no choice" in str(refused.value)


def test_the_consult_tool_refuses_a_one_option_card_in_its_arguments() -> None:
    tool = registered_tools(build_lead_agent().toolsets)["consult_user"]

    with pytest.raises(ValidationError, match="which is no choice"):
        tool.function_schema.validator.validate_python(
            {
                "questions": [_FUNGIDB_CARD],
                "reply": "Please confirm the new threshold on the card.",
            }
        )


def test_a_free_text_card_offers_no_option() -> None:
    card = CardQuestion.model_validate(
        {"id": "q1", "kind": "free_text", "prompt": "Anything else?"}
    )

    assert card.options == []


_SPORES = requirement(
    ConstraintKind.OTHER, "expression in spores", "expressed in spores"
)
_SUBSTITUTE_CARD = CardQuestion.model_validate(
    {
        "id": "spore_expression_scope",
        "kind": "single_choice",
        "prompt": (
            "How should the missing spore-expression condition be handled? The site "
            "has no matching spore-expression search for the requested organism."
        ),
        "options": [
            {
                "label": (
                    "Use the nearest different-organism search only if that "
                    "substitution is scientifically intended."
                )
            },
            {
                "label": (
                    "Do not substitute a different-organism search; leave the "
                    "spore-expression condition unresolved."
                ),
                "recommended": True,
            },
        ],
        "dimension": "other",
    }
)


async def test_a_requirement_the_pass_names_unstated_is_asked_to_drop_or_keep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _signal_peptide_only(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.append(
            Criterion(
                id="c_signal_peptide",
                text="Nosema ceranae BRL01 genes with a signal peptide annotation",
                search_name="GenesWithSignalPeptide",
                organism_param="organism",
                resolved_params={
                    "organism": BoundValue(
                        value=MultiPickValue(values=["Vairimorpha ceranae BRL01"]),
                        source="stated",
                    )
                },
                result_count=81,
            )
        )
        return FrameResult(
            summary="The signal peptide search is bound; no search states spores.",
            unstated=["expressed in spores"],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _signal_peptide_only)
    deps = lead_deps(
        pipeline_state(
            "microsporidiadb",
            user_prompt=(
                "Find Nosema ceranae BRL01 genes that have a signal peptide and are "
                "expressed in spores."
            ),
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=[_SPORES]),
        )
    )

    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )

    assert isinstance(result, FrameResult)
    [asked] = deps.state.domain.open_questions
    assert [(o.label, o.binding) for o in asked.options] == [
        ("Drop expressed in spores", Withdraw(constraint_id=_SPORES.key)),
        ("Keep expressed in spores", Keep(constraint_id=_SPORES.key)),
    ]
    with pytest.raises(ModelRetry) as refused:
        refuse_a_card_that_binds_nothing(
            run_context_for(deps, "call_card"), [_SUBSTITUTE_CARD], reply="A card."
        )
    assert (
        "\"No search on this site states 'expressed in spores'. Drop it from the "
        'request?" is not asked with its recorded options' in str(refused.value)
    )


_WINNIE = "Cytauxzoon felis strain Winnie"
_GPI_OR_SIGNAL = requirement(
    ConstraintKind.COMBINATION,
    "evidence combination",
    "predicted GPI anchor OR signal peptide",
)
_GPI_QUESTION = (
    "No catalog search on this site states predicted GPI-anchor genes for "
    "Cytauxzoon felis Winnie. Should I proceed with the available signal-peptide "
    "search alone, or should you specify an alternative evidence type?"
)


def _signal_peptide() -> Criterion:
    return Criterion(
        id="c_signal_peptide",
        text="Cytauxzoon felis Winnie genes with a signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=[_WINNIE]), source="stated"
            )
        },
        result_count=288,
    )


def _winnie_deps() -> Any:
    return lead_deps(
        pipeline_state(
            "piroplasmadb",
            user_prompt=(
                "Cytauxzoon felis Winnie genes with a predicted GPI anchor or a "
                "signal peptide"
            ),
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=[_GPI_OR_SIGNAL]),
        )
    )


async def test_a_pass_that_asks_about_an_unstated_requirement_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The piroplasmadb pass: FRAME asks the question its instructions ask for."""

    async def _needs_user(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.append(_signal_peptide())
        return FrameResult(
            disposition="needs_user",
            summary="No search states a GPI anchor.",
            open_questions=[
                SlotQuestion(
                    question=_GPI_QUESTION,
                    dimension=ConstraintKind.DATA_TYPE,
                    recommended_value="GenesWithSignalPeptide",
                    options=[
                        "Proceed with signal peptide alone",
                        "Specify an alternative evidence type",
                    ],
                )
            ],
            unstated=["predicted GPI anchor"],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _needs_user)
    deps = _winnie_deps()

    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )

    assert isinstance(result, FrameResult)
    [asked] = deps.state.domain.open_questions
    assert (asked.question, [o.binding for o in asked.options]) == (
        _GPI_QUESTION,
        [
            Withdraw(constraint_id=_GPI_OR_SIGNAL.key),
            Keep(constraint_id=_GPI_OR_SIGNAL.key),
        ],
    )
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert [(c.id, c.result_count) for c in spec.criteria] == [
        ("c_signal_peptide", 288)
    ]


async def test_a_refused_pass_keeps_the_criteria_it_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The vectorbase pass named a slot its draft does not hold."""

    async def _unheld_slot(**kwargs: Any) -> FrameResult:
        draft = kwargs["agent_deps"].agent_state.operational_spec_draft
        draft.criteria.append(_signal_peptide())
        return FrameResult(
            disposition="needs_user",
            summary="Which location?",
            open_questions=[
                SlotQuestion(
                    question="Which chromosome holds the region?",
                    dimension=ConstraintKind.OTHER,
                    recommended_value="1",
                    criterion_id="c_sex_region",
                    param_name="chromosomeOptional",
                    options=["1", "2"],
                )
            ],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _unheld_slot)
    deps = _winnie_deps()

    with pytest.raises(ModelRetry, match="options that bind nothing"):
        await run_frame(
            deps=deps,
            parent_tool_call_id="t1",
            work_order=frame_work_order("go", deps),
        )

    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["c_signal_peptide"]
