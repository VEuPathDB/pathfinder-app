"""A reply over a column read that named a transform to a countable column counts
by it, offers it or asks; only a read that names none leaves the count unmade."""

from __future__ import annotations

from pathfinder.ai.lead.limit_messages import unfollowed_reach_message
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.column_reach import ReachedColumn, StepReach, TransformReach
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.domain.tally_facts import TallyFact
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    kinds,
    reading_deps,
    reply,
)

GROUP_STEP = 227288240
FROM_GROUPS = TransformReach(
    search_name="FromGroups",
    display_name="Transform Groups to Proteins",
    record_type="sequence",
    countable=1,
    columns=[ReachedColumn(name="abbreviation", display_name="Taxon Code")],
)
TURN_TWO_REPLY = (
    "However, its records are ortholog groups, and the result does not carry a "
    "countable Plasmodium-species field. That means the site cannot provide a "
    "species breakdown or identify the largest species from this result as it "
    "stands."
)


def _read(transforms: list[TransformReach]) -> LeadDeps:
    deps = reading_deps()
    deps.state.turn_markers.column_reaches.append(
        StepReach(wdk_step_id=GROUP_STEP, record_type="group", transforms=transforms)
    )
    return deps


def test_a_reply_that_leaves_a_reached_count_unmade_is_refused() -> None:
    deps = _read([FROM_GROUPS])

    mismatches = reconcile(reply(TURN_TWO_REPLY), turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in mismatches] == [
        (
            "unfollowed_reach",
            (
                "step_columns found no countable column on step 227288240 (group "
                "records), and a transform reaches one: FromGroups (Transform "
                "Groups to Proteins) turns them into sequence records, which count "
                "by abbreviation (Taxon Code). Add the transform with edit_strategy "
                "and count the new step with count_step_by_column, or offer the "
                "transform on a card. The site does not lack this count."
            ),
        )
    ]
    assert mismatches[0].sentence == unfollowed_reach_message(
        StepReach(wdk_step_id=GROUP_STEP, record_type="group", transforms=[FROM_GROUPS])
    )


def test_a_read_that_no_transform_reaches_leaves_the_limit_standing() -> None:
    unreached = FROM_GROUPS.model_copy(update={"countable": 0, "columns": []})

    assert "unfollowed_reach" not in kinds(_read([unreached]), reply(TURN_TWO_REPLY))


def test_a_count_made_after_the_read_follows_it() -> None:
    deps = _read([FROM_GROUPS])
    deps.state.turn_markers.record_tally(
        TallyFact(
            id="orthomcl-step-1-abbreviation",
            title="Sequences by Taxon Code",
            record_noun="sequence",
            total=1,
            distinct=1,
        )
    )

    assert "unfollowed_reach" not in kinds(deps, reply(TURN_TWO_REPLY))


def test_a_reply_that_asks_about_the_transform_stands() -> None:
    question = AskedQuestion(
        question="Shall I turn the groups into proteins and count them by taxon?",
        dimension=ConstraintKind.OTHER,
        recommended_value="turn the groups into proteins",
    )

    assert "unfollowed_reach" not in kinds(
        _read([FROM_GROUPS]), reply(TURN_TWO_REPLY, questions=[question])
    )
