"""An analysis step's row carries the compute's groups, variable and cuts,
each with who set it, the way a search step's row carries its values."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.strategy import flatten_tree

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding, CutTallies
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import ParameterFact
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    domain_answering,
    lead_deps,
    pipeline_state,
)
from pathfinder.tests.unit.domain.strategy._analysis import (
    EXPORTED,
    analysed,
    binding,
    exported_step,
)

_NOT_MEASURED = "its count at another value is not measured"


def _deps(prompt: str, bound: AnalysisBinding | None = None) -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="24h", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(exported_step())
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={EXPORTED: 201})
    state = pipeline_state(
        "plasmodb",
        user_prompt=prompt,
        user_message_id=uuid4(),
        domain=domain_answering(OperationalSpec(criteria=[analysed(bound=bound)])),
    )
    return lead_deps(state, strategy_session=session)


def test_the_analysis_step_row_carries_the_compute_values() -> None:
    [step] = turn_facts(
        _deps("Genes higher at 24h than at 18h in the DHC time course.")
    ).steps

    assert step.parameters == [
        ParameterFact(
            name="group_a", display_name="Reference group", value="18h", source="stated"
        ),
        ParameterFact(
            name="group_b", display_name="Compared group", value="24h", source="stated"
        ),
        ParameterFact(
            name="method",
            display_name="Method",
            value="DESeq",
            source="chosen",
            notes=[_NOT_MEASURED],
        ),
        ParameterFact(
            name="value_variable",
            display_name="Measured variable",
            value="SEQUENCE_READ_COUNT_SENSE",
            source="chosen",
            notes=[_NOT_MEASURED],
        ),
        ParameterFact(
            name="effect_direction",
            display_name="Effect direction",
            value="upOnly",
            label="Genes higher in 24h than in 18h",
            source="chosen",
            notes=[_NOT_MEASURED],
        ),
        ParameterFact(
            name="effect_size_threshold",
            display_name="Effect size threshold",
            value="1",
            source="chosen",
            notes=[_NOT_MEASURED],
        ),
        ParameterFact(
            name="significance_threshold",
            display_name="Significance threshold",
            value="0.05",
            source="chosen",
            notes=[_NOT_MEASURED],
        ),
    ]


def test_a_cut_the_researcher_wrote_is_stated() -> None:
    [step] = turn_facts(
        _deps("Genes up at 24h over 18h, log2 fold change 1, p below 0.05, DESeq.")
    ).steps

    assert {p.name: p.source for p in step.parameters} == {
        "group_a": "stated",
        "group_b": "stated",
        "method": "stated",
        "value_variable": "chosen",
        "effect_direction": "chosen",
        "effect_size_threshold": "stated",
        "significance_threshold": "stated",
    }


def _threshold_row(prompt: str, threshold: float) -> ParameterFact:
    labelled = binding().model_copy(
        update={
            "effect_size_label": "log2(Fold Change)",
            "effect_size_threshold": threshold,
        }
    )
    [step] = turn_facts(_deps(prompt, labelled)).steps
    [row] = [p for p in step.parameters if p.name == "effect_size_threshold"]
    return row


def test_a_fold_bound_at_its_log2_is_stated_and_shows_both() -> None:
    row = _threshold_row("loosen the fold change to 1.5-fold", 0.585)

    assert (row.lines(), row.source) == (
        ["log2(Fold Change): 0.585 (1.5-fold)"],
        "stated",
    )


def test_a_folds_number_bound_on_the_log2_scale_is_chosen_and_shows_its_fold() -> None:
    row = _threshold_row("Loosen it to 1.5-fold.", 1.5)

    assert (row.lines(), row.source) == (
        ["log2(Fold Change): 1.5 (2.83-fold)", _NOT_MEASURED],
        "chosen",
    )


# The C. neoformans export: wild type input, 37 on 30, 7,884 genes tested.
_TALLIES = CutTallies(
    tested=7884,
    retained=8,
    retained_up=8,
    retained_down=11,
    at_any_effect=41,
    at_any_significance=230,
)


def _named_and_counted() -> list[ParameterFact]:
    counted = binding().model_copy(
        update={
            "subset": ["VAR_84f17484 is one of wild type"],
            "shown_subset": ["genotype is one of wild type"],
            "value_variable_name": "Count",
            "tallies": _TALLIES,
        }
    )
    [step] = turn_facts(_deps("Genes higher at 24h than at 18h.", counted)).steps
    return step.parameters


def test_the_subset_and_the_measured_variable_are_named_as_the_study_does() -> None:
    rows = {p.name: p.lines()[0] for p in _named_and_counted()}

    assert (rows["subset"], rows["value_variable"]) == (
        "Subset: genotype is one of wild type",
        "Measured variable: SEQUENCE_READ_COUNT_SENSE (Count)",
    )


def test_each_chosen_cut_shows_its_count_beside_the_count_at_the_other_reading() -> (
    None
):
    notes = {p.name: p.notes for p in _named_and_counted()}

    assert (
        notes["effect_size_threshold"],
        notes["significance_threshold"],
        notes["effect_direction"],
    ) == (
        ["Effect size threshold at the chosen 1: 8 of 7,884 genes tested; at 0: 41"],
        ["Significance threshold at the chosen 0.05: 8 genes; at 1: 230"],
        [
            (
                "Effect direction at the chosen upOnly: 8 genes; 8 higher in the "
                "compared group, 11 higher in the reference group"
            )
        ],
    )
