from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.domain.strategy.computed_groups import SNAPSHOT_NOTE
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.strategy_description import (
    derived_description,
    shown_description,
    stated_description,
    strategy_description,
)

_SIGNAL = StrategyStep(
    id="signal",
    kind=StepKind.SEARCH,
    search_name="GenesWithSignalPeptide",
    display_name="Predicted Signal Peptide",
)
_GO = StrategyStep(
    id="go", kind=StepKind.SEARCH, search_name="GenesByGoTerm", display_name="GO Term"
)
_JOIN = StrategyStep(
    id="join",
    kind=StepKind.COMBINE,
    search_name="__combine__",
    operator=CombineOp.INTERSECT,
    primary_input_id="signal",
    secondary_input_id="go",
)


def _graph(*steps: StrategyStep, stated: str | None = None) -> StrategyGraph:
    graph = StrategyGraph("g1", "Apicoplast", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = {step.id: step for step in steps}
    graph.description = stated
    return graph


def test_a_graph_with_no_stated_description_reads_its_root() -> None:
    graph = _graph(_SIGNAL, _GO, _JOIN)

    assert strategy_description(graph, "join") == derived_description(
        "transcript", _JOIN
    )
    assert strategy_description(graph, "signal") == (
        "Find transcript results for Predicted Signal Peptide."
    )


def test_a_stated_description_is_sent_as_stated() -> None:
    graph = _graph(_SIGNAL, stated="Signal peptides in 3D7")

    assert strategy_description(graph, "signal") == "Signal peptides in 3D7"


@pytest.mark.parametrize(
    ("stored", "stated"),
    [
        (None, None),
        ("", None),
        ("Find transcript results for Predicted Signal Peptide.", None),
        ("Combine transcript results for intersect.", None),
        (
            f"Find transcript results for Predicted Signal Peptide. {SNAPSHOT_NOTE}",
            SNAPSHOT_NOTE,
        ),
        (SNAPSHOT_NOTE, SNAPSHOT_NOTE),
        ("Signal peptides in 3D7", "Signal peptides in 3D7"),
    ],
)
def test_a_stored_description_keeps_only_what_was_stated(
    stored: str | None, stated: str | None
) -> None:
    assert stated_description(stored) == stated


def test_the_shown_description_reads_the_main_root() -> None:
    graph = _graph(_SIGNAL, _GO, _JOIN)
    graph.recompute_roots()

    assert shown_description(graph) == "Combine transcript results for intersect."


def test_a_graph_with_no_root_shows_only_a_stated_description() -> None:
    assert shown_description(_graph(stated="Signal peptides in 3D7")) == (
        "Signal peptides in 3D7"
    )
