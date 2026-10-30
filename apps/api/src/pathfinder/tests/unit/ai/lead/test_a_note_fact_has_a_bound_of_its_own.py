from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    LeadTurnState,
    hold_the_turn_contract,
)
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.column_reach import ReachedColumn, StepReach, TransformReach
from pathfinder.domain.reply_note import render_note
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
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
                SiteCheckGap(
                    check=SiteCheck(
                        kind=ConstraintKind.ORGANISM,
                        subject="Plasmodium species",
                        status="fail",
                        evidence="no step restricts the groups to Plasmodium",
                        requirement=ORGANISM.key,
                    )
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


def test_a_note_number_past_the_bound_is_shown_marked_unchecked() -> None:
    deps = reading_deps()
    ctx = replace(run_context_for(deps), retry=3)
    answer = reply("It returns 66 genes.", next_state="complete", questions=[QUESTION])

    assert hold_the_turn_contract(ctx, answer) == answer
    assert deps.state.turn_markers.unchecked_reply is True


def test_a_note_number_within_the_bound_is_refused_with_the_number() -> None:
    message = _correction(reading_deps(), 0, "It returns 66 genes.", "await_user")

    assert "``66``" in message


def test_a_turn_that_read_nothing_from_a_site_writes_its_note_freely() -> None:
    deps = blame_deps()
    answer = reply("A genome of 23 Mb holds 14 chromosomes.")

    assert hold_the_turn_contract(run_context_for(deps), answer) == answer
    assert deps.state.turn_markers.unchecked_reply is False


def test_a_link_past_the_bound_never_reaches_the_reader() -> None:
    deps = reading_deps()
    ctx = replace(run_context_for(deps), retry=3)
    answer = reply("Read [the review](javascript:alert(1)) and https://evil.example.")

    let_through = hold_the_turn_contract(ctx, answer)

    assert isinstance(let_through, LeadResponse)
    assert render_note(let_through.prose, turn_facts(deps)) == "Read the review and ."
    assert deps.state.turn_markers.unchecked_reply is True
