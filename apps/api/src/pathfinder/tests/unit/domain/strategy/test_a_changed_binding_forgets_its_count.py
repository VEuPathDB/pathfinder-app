"""A criterion's count holds for the values it counted, so every change to a
value leaves the count unknown."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_fold import fold_option_criteria
from pathfinder.domain.strategy.spec_hydration import criterion_analysing
from pathfinder.domain.strategy.spec_replay import criterion_rebound, criterion_restated
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.domain.strategy._analysis import COMPUTE_SEARCH, binding

from ._builders import text_leaf

_SEARCH = "GenesByRNASeqEvidence"


def _counted(criterion_id: str = "c_expression") -> Criterion:
    return Criterion(
        id=criterion_id,
        text="upregulated in gametocytes",
        search_name=_SEARCH,
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=["Pf3D7"]),
                "dataset": StringValue(value="all_rnaseq"),
            },
            defaulted=["dataset"],
        ),
        result_count=627,
    )


def test_a_restated_value_forgets_the_count() -> None:
    restated = criterion_restated(
        _counted(),
        "dataset",
        StringValue(value="pfal3D7_Sexual_Stage_rnaSeq"),
        sheet=(),
    )

    assert (restated.param_values["dataset"], restated.result_count) == (
        StringValue(value="pfal3D7_Sexual_Stage_rnaSeq"),
        None,
    )


def test_a_rebound_search_forgets_the_count() -> None:
    rebound = criterion_rebound(_counted(), text_leaf(), None)

    assert (rebound.search_name, rebound.result_count) == ("GenesByText", None)


def test_an_analysis_forgets_the_count() -> None:
    analysing = criterion_analysing(_counted(), COMPUTE_SEARCH, binding())

    assert (analysing.search_name, analysing.result_count) == (COMPUTE_SEARCH, None)


def test_a_carried_option_forgets_the_carriers_count() -> None:
    option = Criterion(
        id="c_option",
        text="use the gametocyte timecourse dataset",
        search_name=_SEARCH,
        resolved_params=bound(
            {"dataset": StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq")}
        ),
    )
    spec = OperationalSpec(
        criteria=[_counted(), option],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_expression")
        ),
    )

    (carrier,) = fold_option_criteria(spec).spec.criteria

    assert (carrier.param_values["dataset"], carrier.result_count) == (
        StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq"),
        None,
    )


_GO = "GO:0042540 : hemoglobin catabolic process : 7"


def test_an_option_that_restates_the_carriers_values_carries_nothing() -> None:
    """The plasmodb GO step: the comparison option holds the same GO values."""
    held = {
        "go_typeahead": MultiPickValue(values=["GO:0042540"]),
        "go_term_evidence": MultiPickValue(values=["Curated", "Computed"]),
    }
    carrier = Criterion(
        id="step_go",
        text="hemoglobin catabolic process",
        search_name="GenesByGoTerm",
        resolved_params={
            **bound(held, chosen={"go_typeahead": "the stated process"}),
            **bound({"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])}),
        },
        measurements=[
            Measurement(kind="vocabulary_label", param="go_typeahead", label=_GO)
        ],
        result_count=7,
    )
    option = Criterion(
        id="c_original_plasmodium",
        text="the original Plasmodium-wide comparison",
        search_name="GenesByGoTerm",
        resolved_params={
            **bound(held, chosen={"go_typeahead": "keeps the same GO term"}),
            **bound({"organism": MultiPickValue(values=["Plasmodium"])}),
        },
    )
    spec = OperationalSpec(
        criteria=[carrier, option],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_go")
        ),
    )

    (folded,) = fold_option_criteria(spec).spec.criteria

    assert (
        folded.resolved_params["go_typeahead"].carried_from,
        folded.measurements,
        folded.result_count,
    ) == ("", carrier.measurements, 7)


def test_an_option_with_the_carriers_wire_value_keeps_the_carriers_label() -> None:
    """The fold carries a value only when its wire form differs."""
    labelled = BoundValue(
        value=MultiPickValue(values=["GO:0042540"]),
        source="chosen",
        label="hemoglobin catabolic process",
    )
    carrier = Criterion(
        id="step_go",
        text="hemoglobin catabolic process",
        search_name="GenesByGoTerm",
        resolved_params={"go_typeahead": labelled},
        result_count=7,
    )
    option = Criterion(
        id="c_option",
        text="the same GO term",
        search_name="GenesByGoTerm",
        resolved_params={
            "go_typeahead": BoundValue(
                value=MultiPickValue(values=["GO:0042540"]), source="stated"
            )
        },
    )
    spec = OperationalSpec(
        criteria=[carrier, option],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_go")
        ),
    )

    (folded,) = fold_option_criteria(spec).spec.criteria

    assert (folded.resolved_params["go_typeahead"], folded.result_count) == (
        labelled,
        7,
    )
