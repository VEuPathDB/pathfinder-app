"""The contract rule over a turn whose last pass did not run."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    LeadResponse,
    reconcile,
    turn_record,
)
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    CLEAN_REPLY,
    building_deps,
    reading_deps,
    reply,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    call_then_final_model,
    lead_deps,
    pipeline_state,
    user_intent,
)

# A reply that names the next pass, asks nothing, and ends the turn.
PROMISES_THE_NEXT_PASS = (
    "I'll keep the existing annotation candidates as the starting set and "
    "apply the relaxed representative-species ortholog screen next."
)
# What the run records for a dispatch tool it refused and never ran again.
A_REFUSED_EDIT = {"edit_strategy": 2}
A_BUDGET_STOP = PhaseStop(
    role="frame",
    reason=PhaseStopReason.BUDGET,
    tool_calls=60,
    criteria_bound=0,
    criteria_declared=4,
)
THE_CHOICE = OpenQuestion(
    question="Should the ortholog screen keep the strict species list?",
    dimension=ConstraintKind.ORGANISM,
    recommended_value="the relaxed representative list",
)


def mismatches_after(
    deps: LeadDeps,
    report: LeadResponse,
    *,
    refused: dict[str, int] | None = None,
) -> list[tuple[str, str]]:
    """The kind and the sentence of every mismatch, over a turn whose run
    refused the dispatch tools in ``refused``."""
    ctx = replace(run_context_for(deps), retries=dict(refused or {}))
    return [(m.kind, m.sentence) for m in reconcile(report, turn_record(ctx))]


def kinds_after(
    deps: LeadDeps,
    report: LeadResponse,
    *,
    refused: dict[str, int] | None = None,
) -> list[str]:
    return [kind for kind, _ in mismatches_after(deps, report, refused=refused)]


class TestTheRecordOfARefusedDispatch:
    def test_the_record_names_the_dispatch_the_run_refused(self) -> None:
        ctx = replace(run_context_for(reading_deps()), retries=A_REFUSED_EDIT)

        assert turn_record(ctx).refused_dispatches == ("edit_strategy",)

    def test_a_tool_that_is_not_a_dispatch_is_not_one(self) -> None:
        ctx = replace(
            run_context_for(reading_deps()),
            retries={"read_gene_record": 1},
        )

        assert turn_record(ctx).refused_dispatches == ()


class TestTheUnfinishedWorkRule:
    def test_a_reply_that_announces_the_refused_pass_is_a_mismatch(self) -> None:
        found = mismatches_after(
            reading_deps(),
            reply(PROMISES_THE_NEXT_PASS),
            refused=A_REFUSED_EDIT,
        )

        assert [kind for kind, _ in found] == ["unfinished_work"]
        sentence = found[0][1]
        assert "edit_strategy" in sentence
        assert "asked_questions" in sentence

    def test_a_reply_that_records_the_choice_stands(self) -> None:
        report = reply(PROMISES_THE_NEXT_PASS, questions=[THE_CHOICE])

        assert kinds_after(reading_deps(), report, refused=A_REFUSED_EDIT) == []

    def test_a_turn_whose_dispatches_all_ran_stands(self) -> None:
        assert kinds_after(reading_deps(), reply(PROMISES_THE_NEXT_PASS)) == []

    def test_a_turn_that_built_stands(self) -> None:
        report = reply(PROMISES_THE_NEXT_PASS, changed=True)

        assert kinds_after(building_deps(), report, refused=A_REFUSED_EDIT) == []

    def test_a_pass_stopped_on_its_budget_is_the_same_unfinished_work(self) -> None:
        deps = reading_deps()
        deps.last_phase_stop = A_BUDGET_STOP

        found = mismatches_after(deps, reply(CLEAN_REPLY))

        assert [kind for kind, _ in found] == ["unfinished_work"]
        assert "the framing pass stopped on its call budget" in found[0][1]

    def test_a_resolved_turn_stands(self) -> None:
        report = reply(PROMISES_THE_NEXT_PASS, next_state="complete")

        assert kinds_after(reading_deps(), report, refused=A_REFUSED_EDIT) == []


def _asking_for_a_strategy() -> LeadDeps:
    """A turn whose message asks for a strategy the thread does not hold."""
    deps = lead_deps(
        pipeline_state(
            user_prompt="Build me the ortholog screen.",
            user_message_id=uuid4(),
        ),
        intent=user_intent(IntentClassification.NEW_STRATEGY),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _retry_prompts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.model_response()
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


class TestTheRefusalTheLeadRunRecords:
    """The rule reads the run's own retry record, over the Lead's real wiring."""

    def test_a_dispatch_the_run_refused_makes_the_reply_come_back_once(self) -> None:
        deps = _asking_for_a_strategy()
        model = call_then_final_model(
            "build_strategy",
            {},
            {
                "prose": PROMISES_THE_NEXT_PASS,
                "nextState": "await_user",
                "strategyChanged": False,
            },
        )

        result = asyncio.run(
            build_lead_agent().run(deps.state.user_prompt, deps=deps, model=model),
        )

        assert isinstance(result.output, LeadResponse)
        assert deps.state.turn_markers.contract_refused is True
        corrections = [
            text
            for text in _retry_prompts(result.all_messages())
            if CONTRACT_HEADING in text
        ]
        assert len(corrections) == 1
        assert "build_strategy refused this turn's call" in corrections[0]
