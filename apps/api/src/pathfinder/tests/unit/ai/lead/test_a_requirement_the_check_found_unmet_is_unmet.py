"""A requirement the check found nothing in the strategy answers is unmet in the
ledger, leaves the tree to the build, and never ends the turn complete."""

from __future__ import annotations

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.limit_messages import unmet_requirement_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.caveats import Gap, RequirementGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps, reply
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium species",
    label="organism scope",
    source=ConstraintSource.USER_EXPLICIT,
)
UNMET = RequirementGap(text="Plasmodium species", status="unmet", key=ORGANISM.key)
UNSHOWN = RequirementGap(text="Plasmodium species", status="unshown", key=ORGANISM.key)
UNNAMED = RequirementGap(text="Plasmodium species", status="unmet")
RENAMED = RequirementGap(text="species of Plasmodium", status="unmet", key=ORGANISM.key)
SPEC = OperationalSpec(
    goal="Which Plasmodium species has the most singleton genes?",
    constraints=[ORGANISM],
    criteria=[
        Criterion(
            id="step_88b8197d",
            text="singleton ortholog groups containing exactly one protein",
            search_name="GroupsBySequenceCount",
        )
    ],
)
TURN_ONE_REPLY = (
    "The strategy correctly defines singleton groups as groups containing exactly "
    "one protein and returns [count:step_88b8197d]."
)


def _digest(gaps: list[Gap]) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.HANDOFF,
        prose="Checked.",
        reason="The current search does not express Plasmodium scope.",
        success=False,
        gaps=gaps,
    )


def _checked(state: PipelineState, gaps: list[Gap]) -> PipelineState:
    domain = state.domain
    domain.record_verdict(
        _digest(gaps), revision=strategy_revision(domain.answered_graph)
    )
    return state


def _groups_state() -> PipelineState:
    return pipeline_state("orthomcl", domain=StrategyDomainState(operational_spec=SPEC))


def test_a_requirement_the_check_found_unmet_blocks_in_the_ledger() -> None:
    before = derive_ledger(_groups_state(), None).constraints
    after = derive_ledger(_checked(_groups_state(), [UNMET]), None).constraints

    assert [(g.status, g.note) for g in before.grounded] == [
        (ConstraintStatus.GROUNDED, "")
    ]
    assert [(g.status, g.note) for g in after.grounded] == [
        (
            ConstraintStatus.UNGROUNDABLE,
            "the check found nothing in the strategy answers it",
        )
    ]
    assert (after.blocking, after.unmet_count) == (True, 1)


def test_the_ledger_and_the_tree_read_the_same_gaps() -> None:
    renamed = derive_ledger(_checked(_groups_state(), [RENAMED]), None).constraints
    unnamed = derive_ledger(_checked(_groups_state(), [UNNAMED]), None).constraints

    assert (renamed.blocking, _digest([RENAMED]).blames_the_tree) == (True, True)
    assert (unnamed.blocking, _digest([UNNAMED]).blames_the_tree) == (False, False)


def test_a_requirement_no_record_shows_stays_grounded() -> None:
    held = derive_ledger(_checked(_groups_state(), [UNSHOWN]), None).constraints

    assert (held.blocking, held.unmet_count) == (False, 0)


def test_an_unmet_requirement_blames_the_tree_and_an_unshown_one_does_not() -> None:
    assert (_digest([UNMET]).blames_the_tree, _digest([UNSHOWN]).blames_the_tree) == (
        True,
        False,
    )


def _unmet_deps() -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.operational_spec = SPEC
    _checked(deps.state, [UNMET])
    return deps


def test_a_reply_that_ends_the_turn_complete_over_it_is_refused() -> None:
    record = turn_record(run_context_for(_unmet_deps()))

    found = {
        m.kind: m.sentence
        for m in reconcile(reply(TURN_ONE_REPLY, next_state="complete"), record)
    }

    assert found["unmet_requirement"] == unmet_requirement_message(
        ("Plasmodium species",)
    )
    assert found["unmet_requirement"] == (
        "The researcher stated 'Plasmodium species', and the strategy does not "
        "answer it, so the turn is not complete. Set nextState to await_user and "
        "say in the reply that 'Plasmodium species' stays unmet. When a search can "
        "state it, apply it with edit_strategy first."
    )


def test_a_reply_that_waits_on_the_researcher_over_it_stands() -> None:
    record = turn_record(run_context_for(_unmet_deps()))

    found = [m.kind for m in reconcile(reply(TURN_ONE_REPLY), record)]

    assert "unmet_requirement" not in found


def test_a_card_over_an_unmet_requirement_is_not_refused() -> None:
    deps = _unmet_deps()
    card = DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name="consult_user",
                args={
                    "questions": [],
                    "reply": "Nothing in the strategy restricts the groups to "
                    "Plasmodium species yet.",
                },
                tool_call_id="call_card",
            )
        ]
    )

    assert hold_the_contract_on_a_card(run_context_for(deps), card) is None
    assert deps.state.turn_markers.refused_rules == []
