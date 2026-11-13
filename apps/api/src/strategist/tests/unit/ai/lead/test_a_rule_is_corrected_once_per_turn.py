from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.exceptions import ModelRetry

from strategist.ai.graph.state import PhaseDisposition, VerificationDigest
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import (
    LeadResponse,
    LeadTurnState,
    hold_the_turn_contract,
)
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.column_reach import ReachedColumn, StepReach, TransformReach
from strategist.domain.reply_note import render_note
from strategist.domain.site_checks import SiteCheck, SiteCheckGap
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.revision import strategy_revision
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead._turn_contract_cases import (
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
HONEST = "The strategy leaves Plasmodium species unmet."


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
                        requirement=ORGANISM.id,
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


def test_each_rule_is_corrected_once_and_the_third_answer_stands() -> None:
    deps = _unmet_and_unfollowed()

    first = _correction(deps, 0, HONEST, "await_user")
    second = _correction(deps, 1, HONEST, "complete")
    ctx = replace(run_context_for(deps), retry=2)
    third = reply(HONEST, next_state="await_user")

    assert ("step_columns found" in first, "The researcher stated" in first) == (
        True,
        False,
    )
    assert ("step_columns found" in second, "The researcher stated" in second) == (
        False,
        True,
    )
    assert hold_the_turn_contract(ctx, third) == third
    assert deps.state.turn_markers.refused_rules == [
        "unfollowed_reach",
        "unmet_requirement",
    ]
    assert deps.state.turn_markers.output_refusals == 2


def test_a_model_written_link_reaches_the_renderer_unchanged() -> None:
    deps = reading_deps()
    answer = reply("Read [the review](javascript:alert(1)) and https://evil.example.")

    let_through = hold_the_turn_contract(run_context_for(deps), answer)

    assert isinstance(let_through, LeadResponse)
    assert render_note(let_through.prose, turn_facts(deps)) == (
        "Read [the review](javascript:alert(1)) and https://evil.example."
    )
