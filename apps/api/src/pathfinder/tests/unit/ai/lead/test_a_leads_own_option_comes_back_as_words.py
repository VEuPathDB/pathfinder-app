from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.guarantees import registered_tools
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_WIDEN = CardQuestion(
    id="q1",
    prompt=(
        "The intersection of UKMEL1 signal-peptide genes with the C. hominis TU502 "
        "oocyst-expression proxy returned no genes. Which available expression "
        "setting should I relax for a broader result?"
    ),
    dimension=ConstraintKind.PERCENTILE,
    options=[
        ConsultOption(label="Minimum expression percentile: 0"),
        ConsultOption(label="Protein Coding Only: all"),
    ],
)
_PROXY = Criterion(
    id="c_oocyst_expression_proxy",
    text="expressed in oocysts",
    search_name="GenesByRNASeqchomTU502_Lippuner_Oocyst_ebi_rnaSeq_RSRC",
    resolved_params={
        "min_expression_percentile": BoundValue(
            value=StringValue(value="80"), source="chosen"
        )
    },
)


def test_the_leads_card_reaches_the_researcher_unchecked() -> None:
    tool = registered_tools(build_lead_agent().toolsets)["consult_user"]

    assert [tool.args_validator] == [None]


async def test_a_picked_option_that_binds_nothing_comes_back_as_the_answer() -> None:
    spec = OperationalSpec(criteria=[_PROXY])
    deps = lead_deps(
        pipeline_state(
            "cryptodb",
            user_prompt="an answer to the card",
            user_message_id=uuid4(),
            domain=StrategyDomainState(operational_spec=spec),
        )
    )
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    picked = UserQuestionAnswer(
        question_id="q1",
        prompt=_WIDEN.prompt,
        chosen_labels=["Minimum expression percentile: 0"],
    )
    deps.state.user_question_answers = {"call_card": [picked]}

    returned = await consult_user(
        run_context_for(deps, "call_card"), [_WIDEN], reply="A card."
    )

    assert returned.return_value == [picked]
    assert deps.state.domain.operational_spec == spec
