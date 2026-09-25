"""A request only the portal answers is sent to a new portal conversation, and
no pass or reply offers a site switch: a conversation is bound to its site."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_lead_gives_the_portal_sentence_and_offers_no_switch() -> None:
    lead = _flat(LEAD_INSTRUCTIONS)

    assert "**A request only the VEuPathDB Portal answers opens there.**" in lead
    assert (
        "A conversation is bound to its site, so never offer, ask about or confirm "
        "a site switch, in prose or on a card." in lead
    )
    assert "give that sentence word for word, link included" in lead


def test_frame_records_no_question_for_a_portal_only_transform() -> None:
    frame = _flat(_FRAME_INSTRUCTIONS)

    assert (
        "Bind the organism the request names even when the sheet does not list "
        "it: a transform to an organism this site's transform does not reach is "
        "refused with the portal's sentence: bind nothing for it, ask no question "
        "about it, and copy that sentence into the summary word for word, link "
        "included." in frame
    )
    assert "Switching sites" not in frame


_ROUTE = (
    "This needs the VEuPathDB Portal, where one strategy holds both organisms. "
    "[Open a new conversation there](/veupathdb/conversation); this conversation "
    "stays on PlasmoDB."
)
_SWITCH = OpenQuestion(
    question=(
        "Would you like to continue this mapping in the VEuPathDB Portal, where "
        "Plasmodium falciparum 3D7 and Toxoplasma gondii ME49 can be held in one "
        "strategy?"
    ),
    dimension=ConstraintKind.ORGANISM,
    recommended_value="Continue in the VEuPathDB Portal",
)


def _portal_only_pass(monkeypatch: pytest.MonkeyPatch, question: bool) -> None:
    """A pass the organism refusal sent to the portal, binding nothing."""

    async def _stub(*, agent_deps: AgentDeps, **_kwargs: object) -> FrameResult:
        agent_deps.agent_state.portal_route = _ROUTE
        return FrameResult(
            disposition="needs_user",
            summary="The orthology step needs the portal.",
            open_questions=[_SWITCH] if question else [],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)


def _seeded() -> LeadDeps:
    deps = lead_deps(
        pipeline_state(user_prompt="Carry these to Toxoplasma gondii ME49.")
    )
    deps.state.domain.operational_spec = OperationalSpec(
        goal="signal peptide genes",
        criteria=[
            Criterion(
                id="c_sp", text="signal peptide", search_name="GenesWithSignalPeptide"
            )
        ],
    )
    return deps


@pytest.mark.parametrize("question", [True, False])
async def test_a_pass_sent_to_the_portal_answers_with_the_sentence_and_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, question: bool
) -> None:
    _portal_only_pass(monkeypatch, question)
    deps = _seeded()

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order="carry the genes to Toxoplasma gondii ME49",
    )

    assert result == FrameResult(disposition="needs_user", summary=_ROUTE)
    assert deps.state.domain.open_questions == []


async def test_a_pass_that_bound_more_carries_the_sentence_ahead_of_its_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _stub(*, agent_deps: AgentDeps, **_kwargs: object) -> FrameResult:
        agent_deps.agent_state.portal_route = _ROUTE
        agent_deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(id="c_tm", text="2 to 99 TM domains", search_name="GenesByTM")
        )
        return FrameResult(disposition="spec_ready", summary="c_tm bound.")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    deps = lead_deps(pipeline_state(user_prompt="Find TM genes and carry them."))

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order="find the genes and carry them to Toxoplasma gondii ME49",
    )

    assert result == FrameResult(
        disposition="spec_ready", summary=f"{_ROUTE} c_tm bound."
    )
