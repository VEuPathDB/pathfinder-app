"""A tally of a step a transform-only chain sits above names both ways back to
the result, and the column hint offers no transform back to that step."""

from __future__ import annotations

from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.ai.lead.limit_messages import unfollowed_reach_message
from pathfinder.ai.lead.reference_fault_messages import reference_sentence
from pathfinder.domain.column_reach import ReachedColumn, StepReach, TransformReach
from pathfinder.domain.reply_references import prose_faults
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact
from pathfinder.domain.tally_paths import StepAbove, TallyPath, tally_paths
from pathfinder.domain.turn_facts import TurnFacts

_STEPS = {
    "step_74948e37": StrategyStep(
        id="step_74948e37",
        kind=StepKind.SEARCH,
        search_name="GroupsBySequenceCount",
        record_class="group",
    ),
    "step_dc53498e": StrategyStep(
        id="step_dc53498e",
        kind=StepKind.TRANSFORM,
        search_name="FromGroups",
        record_class="sequence",
        primary_input_id="step_74948e37",
    ),
    "step_6d2035f5": StrategyStep(
        id="step_6d2035f5",
        kind=StepKind.SEARCH,
        search_name="ByTaxonomy",
        record_class="sequence",
    ),
    "step_5d07de44": StrategyStep(
        id="step_5d07de44",
        kind=StepKind.COMBINE,
        primary_input_id="step_dc53498e",
        secondary_input_id="step_6d2035f5",
    ),
    "c_proteins_to_groups": StrategyStep(
        id="c_proteins_to_groups",
        kind=StepKind.TRANSFORM,
        search_name="GroupsFromSequences",
        record_class="group",
        display_name="Transform Proteins to Groups",
        primary_input_id="step_5d07de44",
    ),
}
_WDK = {
    "step_74948e37": 227288380,
    "step_dc53498e": 227288390,
    "step_6d2035f5": 227288400,
    "step_5d07de44": 227288410,
    "c_proteins_to_groups": 227288420,
}
_PATH = TallyPath(
    tallied_step_id=227288410,
    record_type="sequence",
    above=[
        StepAbove(
            wdk_step_id=227288420,
            display_name="Transform Proteins to Groups",
            transforms_only=True,
        )
    ],
)
_TALLY = TallyFact(
    id="tally_eb2a03e1",
    title="Taxon Code",
    record_noun="proteins",
    total=2744,
    distinct=50,
    rows=[TallyRowFact(value="pyxn", count=898)],
    wdk_step_id=227288410,
    path=_PATH,
)
_REACH = StepReach(
    wdk_step_id=227288420,
    record_type="group",
    transforms=[
        TransformReach(
            search_name="FromGroups",
            display_name="Transform Groups to Proteins",
            record_type="sequence",
            countable=1,
            columns=[ReachedColumn(name="abbreviation", display_name="Taxon Code")],
        )
    ],
)


def test_the_path_holds_the_transform_above_the_tally() -> None:
    assert tally_paths(_STEPS, _WDK, "c_proteins_to_groups", [227288410]) == [_PATH]


def test_the_refusal_names_both_ways_back_to_the_result() -> None:
    facts = TurnFacts(tallies=[_TALLY], result_step_id=227288420)
    [fault] = prose_faults("pyxn leads with [tally:tally_eb2a03e1.pyxn].", facts)

    assert reference_sentence(fault) == (
        "``[tally:tally_eb2a03e1.pyxn]`` counts a step that is not the strategy's "
        "result, as its tally's title says. Either count the result step with "
        'count_step_by_column and cite that tally, or remove "Transform Proteins '
        "to Groups\" with edit_strategy, which only transform the tallied step's "
        "records, so the tallied step is the result again."
    )


def test_the_hint_offers_no_transform_back_to_the_tallied_step() -> None:
    assert unfollowed_reach_message(_REACH, [_PATH]) == (
        "step_columns found no countable column on step 227288420, and a tally "
        'this turn already counted step 227288410, which "Transform Proteins to '
        'Groups" only transform. Remove those steps with edit_strategy so the '
        "tallied step is the result, then cite its tally."
    )
