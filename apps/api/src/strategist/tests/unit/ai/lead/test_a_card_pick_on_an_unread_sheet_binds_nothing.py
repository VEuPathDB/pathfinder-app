from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic import TypeAdapter
from pydantic_ai.messages import ToolReturnPart
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.lead_consult import CardAnswer, consult_user
from strategist.ai.lead.recorded_cards import card_questions
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues, TypedOption
from strategist.domain.strategy.questions import OpenQuestion
from strategist.services.strategies import sheet_params
from strategist.tests._support.record_classes import list_searches_under
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByInterproDomain"
_KINASE = "Protein kinase domain (PF00069)"
_DOWN = WDKError("Service Unavailable", status=503)
_QUESTION = OpenQuestion(
    question="Which InterPro domain should the step search for?",
    options=[
        TypedOption(
            id="pf00069",
            label=_KINASE,
            binding=SetValues(
                criterion_id="c_domain", params={"domain_typeahead": "PF00069"}
            ),
        ),
        TypedOption(
            id="pf00400",
            label="WD domain, G-beta repeat (PF00400)",
            binding=SetValues(
                criterion_id="c_domain", params={"domain_typeahead": "PF00400"}
            ),
        ),
    ],
)


def _criterion() -> Criterion:
    return Criterion(
        id="c_domain",
        text="genes with a protein kinase domain",
        search_name=_SEARCH,
        record_class="transcript",
        resolved_params={
            "domain_database": BoundValue(
                value=MultiPickValue(values=["Pfam"]), source="stated"
            )
        },
    )


async def test_a_pick_on_a_sheet_the_site_did_not_answer_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unanswered(*_args: Any) -> WDKSearch:
        raise _DOWN

    list_searches_under(monkeypatch, "transcript", [_SEARCH])
    monkeypatch.setattr(sheet_params, "read_search_definition", _unanswered)
    deps = lead_deps(
        pipeline_state(
            "plasmodb",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[_criterion()]),
                open_questions=[_QUESTION],
            ),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=_QUESTION.question, chosen_labels=[_KINASE]
            )
        ]
    }

    returned = await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([_QUESTION]),
        reply="One value decides the domain step.",
    )

    part = ToolReturnPart(
        tool_name="consult_user", content=returned.return_value, tool_call_id="c"
    )
    answers = TypeAdapter(list[CardAnswer]).validate_json(part.model_response_str())
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert "domain_typeahead" not in spec.criteria[0].resolved_params
    assert [why for answer in answers for why in answer.refused] == [
        (
            f"the sheet of {_SEARCH} was not read, so {_KINASE!r} binds nothing: "
            "HTTP 503: VEuPathDB service error: Service Unavailable"
        )
    ]
