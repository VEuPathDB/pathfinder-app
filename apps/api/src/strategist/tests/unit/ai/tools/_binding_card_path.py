from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import card_sheets
from strategist.ai.lead.lead_consult import CardAnswer, consult_user
from strategist.ai.lead.recorded_cards import card_questions
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.question_options import SetValues, TypedOption
from strategist.domain.strategy.questions import OpenQuestion
from strategist.services.strategies import sheet_params
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.run_context import run_context_for
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.ai.tools._binding_paths import (
    ORGANISM,
    PF,
    SAMPLES,
    SEARCH,
    VIVAX,
    Case,
    Outcome,
    criterion_holding,
    declared,
    fetcher,
    refused_outcome,
)

_NO_SUCH_WIRE = (
    '{"filters": [{"field": "VAR_36c1c67a", "type": "string", "isRange": false, '
    '"includeUnknown": false, "value": ["No such dataset"]}]}'
)


def _card_wires(case: Case, child: ParamValue) -> dict[str, str]:
    match case:
        case "given_back":
            return {ORGANISM: PF, SAMPLES: to_wire(child)}
        case "left_out":
            return {ORGANISM: PF}
        case "stated_anew":
            return {ORGANISM: PF, SAMPLES: _NO_SUCH_WIRE}
        case "other_case":
            return {ORGANISM: VIVAX.lower()}
        case "other_writing":
            return {ORGANISM: VIVAX}


async def card_pick(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    async def _sheets(
        *, site_id: str, search_names: object
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, search_names
        return {SEARCH: sheet_of(declared({}))}

    monkeypatch.setattr(card_sheets, "parameters_of_searches", _sheets)
    monkeypatch.setattr(sheet_params, "wdk_fetch_at", fetcher)
    wires = _card_wires(case, child)
    question = OpenQuestion(
        question="Which organism should the SNP step read?",
        options=[
            TypedOption(
                id="picked",
                label="Picked",
                binding=SetValues(criterion_id="c_snps", params=wires),
            ),
            TypedOption(
                id="held",
                label="As held",
                binding=SetValues(criterion_id="c_snps", params={ORGANISM: VIVAX}),
            ),
        ],
    )
    deps = lead_deps(
        pipeline_state(
            "plasmodb",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(
                    criteria=[criterion_holding(case, child)]
                ),
                open_questions=[question],
            ),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=["Picked"]
            )
        ]
    }
    answers = returned(
        await consult_user(
            run_context_for(deps, "call_card"),
            questions=card_questions([question]),
            reply="One value decides the SNP step.",
        ),
        list[UserQuestionAnswer],
    )
    refusals = [
        why
        for answer in answers
        for why in CardAnswer.model_validate(answer.model_dump()).refused
    ]
    if refusals:
        return refused_outcome(" ".join(refusals))
    spec = deps.state.domain.operational_spec
    assert spec is not None
    [criterion] = spec.criteria
    return Outcome("accepted", child=criterion.resolved_params[SAMPLES].value)
