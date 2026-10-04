"""A generated strategy name holds while the steps and values it states hold."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
)

from pathfinder.domain.strategy.generated_name import (
    name_outdated,
    name_seed,
    named_steps,
)

NAME = "Naegleria fowleri Peptidase Genes With Signal Peptides"
ORGANISM = "Naegleria fowleri ATCC 30863"


def _peptidase() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_peptidase",
        search_name="GenesByEcNumber",
        parameters={"organism": MultiPickValue(values=[ORGANISM])},
        display_name="EC number",
    )


def _signal(organism: str = ORGANISM) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_signal",
        search_name="GenesWithSignalPeptide",
        parameters={"organism": MultiPickValue(values=[organism])},
        display_name="Signal peptide",
    )


def _both(signal: StrategyStepNode | None = None) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=_peptidase(),
            secondary_input=signal or _signal(),
        ),
        metadata={
            "criterionTexts": {
                "step_peptidase": "peptidase genes",
                "step_signal": "genes with signal peptides",
            }
        },
    )


def _signal_only() -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=_signal(),
        metadata={"criterionTexts": {"step_signal": "genes with signal peptides"}},
    )


def _on_chromosome(chromosome: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_location",
            search_name="GenesByLocation",
            parameters={
                "chromosomeOptional": SinglePickValue(value=chromosome),
                "start_point": StringValue(value="1"),
            },
        ),
    )


MARKED = ["step_peptidase", "step_signal"]


def test_the_name_covers_every_step_but_a_combine() -> None:
    assert named_steps(_both()) == MARKED
    assert named_steps(None) == []


def test_a_deleted_marked_step_outdates_the_name() -> None:
    assert name_outdated(NAME, MARKED, start=_both(), now=_signal_only()) is True


def test_a_marked_step_gone_before_the_turn_outdates_the_name() -> None:
    assert name_outdated(NAME, MARKED, start=_signal_only(), now=_signal_only()) is True


def test_a_strategy_that_keeps_its_marked_steps_keeps_the_name() -> None:
    assert name_outdated(NAME, MARKED, start=_both(), now=_both()) is False


def test_a_deleted_step_the_name_was_not_written_over_keeps_it() -> None:
    assert (
        name_outdated(NAME, ["step_signal"], start=_both(), now=_signal_only()) is False
    )


def test_a_moved_value_the_name_states_outdates_it() -> None:
    name = "Fusarium graminearum P450 Genes on Chromosome 1"

    assert (
        name_outdated(
            name, ["step_location"], start=_on_chromosome("1"), now=_on_chromosome("2")
        )
        is True
    )


def test_a_moved_value_the_name_does_not_state_keeps_it() -> None:
    name = "Fusarium graminearum P450 Genes on Chromosome 1"

    assert (
        name_outdated(
            name,
            ["step_location"],
            start=_on_chromosome("01"),
            now=_on_chromosome("02"),
        )
        is False
    )


def test_a_dropped_pick_the_name_states_in_another_case_outdates_it() -> None:
    start = _both(_signal("naegleria fowleri"))
    now = _both(_signal("Naegleria gruberi"))

    assert name_outdated(NAME, MARKED, start=start, now=now) is True


def test_a_value_moved_on_an_unmarked_step_keeps_the_name() -> None:
    start = _both(_signal("Naegleria fowleri"))
    now = _both(_signal("Naegleria gruberi"))

    assert name_outdated(NAME, ["step_peptidase"], start=start, now=now) is False


def test_the_seed_is_the_organisms_and_the_words_of_the_steps_left() -> None:
    assert name_seed(_signal_only(), [ORGANISM]) == (
        f"{ORGANISM}: genes with signal peptides"
    )


def test_a_step_with_no_words_is_seeded_by_its_label() -> None:
    assert name_seed(_on_chromosome("2")) == "GenesByLocation"


def test_the_seed_joins_the_words_of_every_step_once() -> None:
    assert name_seed(_both()) == "peptidase genes; genes with signal peptides"


def test_a_strategy_with_no_step_seeds_nothing() -> None:
    assert name_seed(None, [ORGANISM]) == ""
