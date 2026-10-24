"""Prose faults are refused on a bound of their own, so a turn whose other rules
were refused still corrects its prose; past the bound only a written number or
a fact the facts lack withholds the reply, which keeps its other fields."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadTurnState, hold_the_turn_contract
from pathfinder.ai.lead.withheld_reply import WITHHELD_ALONE, WITHHELD_REPLY
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.column_reach import ReachedColumn, StepReach, TransformReach
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    blame_deps,
    reading_deps,
    reply,
)

ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium species",
    label="organism scope",
    source=ConstraintSource.USER_EXPLICIT,
)
FROM_GROUPS = TransformReach(
    search_name="FromGroups",
    display_name="Transform Groups to Proteins",
    record_type="sequence",
    countable=1,
    columns=[ReachedColumn(name="abbreviation", display_name="Taxon Code")],
)
QUESTION = AskedQuestion(
    question="Shall I restrict the groups to Plasmodium genomes?",
    dimension=ConstraintKind.ORGANISM,
    recommended_value="Plasmodium genomes",
)
HONEST = "The strategy leaves Plasmodium species unmet."
WRITTEN = "The strategy leaves Plasmodium species unmet across 5 genomes."


def _unmet_and_unfollowed() -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.operational_spec = OperationalSpec(
        goal="Which Plasmodium species has the most singleton genes?",
        constraints=[ORGANISM],
        criteria=[
            Criterion(
                id="step_88b8197d",
                text="singleton ortholog groups",
                search_name="GroupsBySequenceCount",
            )
        ],
    )
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.HANDOFF,
            prose="Checked.",
            reason="No step restricts the groups to Plasmodium.",
            success=False,
            gaps=[
                RequirementGap(
                    text="Plasmodium species", status="unmet", key=ORGANISM.key
                )
            ],
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    deps.state.turn_markers.column_reaches.append(
        StepReach(wdk_step_id=227288240, record_type="group", transforms=[FROM_GROUPS])
    )
    return deps


def _correction(
    deps: LeadDeps, retry: int, prose: str, next_state: LeadTurnState
) -> str:
    ctx = replace(run_context_for(deps), retry=retry)
    with pytest.raises(ModelRetry) as refused:
        hold_the_turn_contract(ctx, reply(prose, next_state=next_state))
    return str(refused.value)


def test_two_rule_refusals_leave_the_prose_its_correction() -> None:
    deps = _unmet_and_unfollowed()

    first = _correction(deps, 0, HONEST, "await_user")
    second = _correction(deps, 1, HONEST, "complete")
    third = _correction(deps, 2, WRITTEN, "await_user")

    assert ("step_columns found" in first, "The researcher stated" in first) == (
        True,
        False,
    )
    assert ("step_columns found" in second, "The researcher stated" in second) == (
        False,
        True,
    )
    assert "``5``" in third
    assert deps.state.turn_markers.refused_rules == [
        "unfollowed_reach",
        "unmet_requirement",
    ]
    assert (
        deps.state.turn_markers.output_refusals,
        deps.state.turn_markers.prose_refusals,
    ) == (2, 1)


def test_a_withheld_reply_keeps_its_question_state_and_reason() -> None:
    deps = blame_deps()
    ctx = replace(run_context_for(deps), retry=3)
    answer = reply("It returns 66 genes.", next_state="complete", questions=[QUESTION])
    answer = answer.model_copy(update={"unverified_reason": "The check stopped."})

    withheld = hold_the_turn_contract(ctx, answer)

    assert withheld == answer.model_copy(update={"prose": WITHHELD_ALONE})


def test_a_withheld_reply_beside_facts_points_at_them() -> None:
    deps = reading_deps()
    ctx = replace(run_context_for(deps), retry=3)

    withheld = hold_the_turn_contract(ctx, reply("It returns 66 genes."))

    assert withheld == reply(WITHHELD_REPLY)


def test_a_shape_fault_past_the_bound_goes_through_unchecked() -> None:
    deps = reading_deps()
    ctx = replace(run_context_for(deps), retry=3)
    answer = reply("The text step returns [count:s3] genes.")

    assert hold_the_turn_contract(ctx, answer) == answer
    assert deps.state.turn_markers.unchecked_reply is True
