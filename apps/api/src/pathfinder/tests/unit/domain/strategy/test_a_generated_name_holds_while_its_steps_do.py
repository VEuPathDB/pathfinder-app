"""A generated strategy name holds while every step and value of its seed holds."""

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
    title_text,
)

ORGANISM = "Naegleria fowleri ATCC 30863"
ORGANISM_WIRE = MultiPickValue(values=[ORGANISM]).to_wire()


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


def _on_chromosome(chromosome: str, *, end: str | None = None) -> StrategyAst:
    parameters = {
        "chromosomeOptional": SinglePickValue(value=chromosome),
        "start_point": StringValue(value="1"),
    }
    if end is not None:
        parameters["end_point"] = StringValue(value=end)
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_location", search_name="GenesByLocation", parameters=parameters
        ),
    )


SEED = {
    "step_peptidase": {"organism": ORGANISM_WIRE},
    "step_signal": {"organism": ORGANISM_WIRE},
}


def test_the_seed_holds_the_wire_value_of_every_step_but_a_combine() -> None:
    assert name_seed(_both()) == SEED
    assert name_seed(None) == {}


def test_a_deleted_seed_step_outdates_the_name() -> None:
    assert name_outdated(SEED, _signal_only()) is True


def test_a_strategy_that_keeps_its_seed_keeps_the_name() -> None:
    assert name_outdated(SEED, _both()) is False


def test_a_deleted_step_outside_the_seed_keeps_the_name() -> None:
    assert name_outdated({"step_signal": SEED["step_signal"]}, _signal_only()) is False


def test_any_moved_seed_value_outdates_the_name() -> None:
    assert name_outdated(name_seed(_on_chromosome("01")), _on_chromosome("02")) is True


def test_a_seed_value_the_step_no_longer_holds_outdates_the_name() -> None:
    seed = name_seed(_on_chromosome("1", end="900"))

    assert name_outdated(seed, _on_chromosome("1")) is True


def test_a_value_added_beside_the_seed_keeps_the_name() -> None:
    seed = name_seed(_on_chromosome("1"))

    assert name_outdated(seed, _on_chromosome("1", end="900")) is False


def test_a_value_moved_on_a_step_outside_the_seed_keeps_the_name() -> None:
    seed = {"step_peptidase": SEED["step_peptidase"]}

    assert name_outdated(seed, _both(_signal("Naegleria gruberi"))) is False


def test_the_title_text_is_the_organisms_and_the_words_of_the_steps_left() -> None:
    assert title_text(_signal_only(), [ORGANISM]) == (
        f"{ORGANISM}: genes with signal peptides"
    )


def test_a_step_with_no_words_is_titled_by_its_label() -> None:
    assert title_text(_on_chromosome("2")) == "GenesByLocation"


def test_the_title_text_joins_the_words_of_every_step_once() -> None:
    assert title_text(_both()) == "peptidase genes; genes with signal peptides"


def test_a_strategy_with_no_step_has_no_title_text() -> None:
    assert title_text(None, [ORGANISM]) == ""
