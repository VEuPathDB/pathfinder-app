"""The answer a build that read nothing gets on the real Lead agent: it passes
unrefused, and the check is the runtime's."""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from strategist.ai.lead.intent import IntentClassification
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import LeadResponse
from strategist.ai.lead.turn_record import owes_a_check
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.tests._support.streamed_model import streamed
from strategist.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    final_result_part,
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

_ZERO_PROMPT = "Find ME49 genes with a signal peptide and a similar profile."
_ZERO_PROSE = "The strategy returned no genes, so here is one way to broaden it."


def _zero_build_deps() -> LeadDeps:
    """A turn whose build pushed one step and read nothing at the root."""
    state = pipeline_state(user_prompt=_ZERO_PROMPT, user_message_id=uuid4())
    state.record_build(BuildOutcome(pushed_step_ids=["step_a"]))
    state.turn_markers.intent_classified = True
    return lead_deps(
        state,
        intent=user_intent(IntentClassification.NEW_STRATEGY),
        strategy_session=session_with_one_step(),
    )


async def test_an_answer_over_a_build_at_zero_is_left_to_the_runtimes_check(
    collector: ChunkCollector,
) -> None:
    del collector
    deps = _zero_build_deps()
    called: list[str] = []

    def _answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        called.append("final_result")
        return ModelResponse(
            parts=[final_result_part({"prose": _ZERO_PROSE, "nextState": "await_user"})]
        )

    result = await build_lead_agent().run(
        _ZERO_PROMPT, deps=deps, model=streamed(_answer, model_name="scripted")
    )

    assert isinstance(result.output, LeadResponse)
    assert (result.output.prose, called, owes_a_check(deps)) == (
        _ZERO_PROSE,
        ["final_result"],
        True,
    )
    assert deps.state.turn_markers.answer_ledger.uses == ()
