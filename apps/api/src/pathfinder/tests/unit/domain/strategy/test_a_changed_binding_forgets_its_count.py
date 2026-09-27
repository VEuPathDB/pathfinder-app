"""A criterion's count holds for the values it counted, so every change to a
value leaves the count unknown."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_fold import fold_option_criteria
from pathfinder.domain.strategy.spec_hydration import criterion_analysing
from pathfinder.domain.strategy.spec_replay import criterion_rebound, criterion_restated
from pathfinder.tests.unit.domain.strategy._analysis import COMPUTE_SEARCH, binding

from ._builders import text_leaf

_SEARCH = "GenesByRNASeqEvidence"


def _counted(criterion_id: str = "c_expression") -> Criterion:
    return Criterion(
        id=criterion_id,
        text="upregulated in gametocytes",
        search_name=_SEARCH,
        resolved_params={
            "organism": MultiPickValue(values=["Pf3D7"]),
            "dataset": StringValue(value="all_rnaseq"),
        },
        defaulted_params=["dataset"],
        result_count=627,
    )


def test_a_restated_value_forgets_the_count() -> None:
    restated = criterion_restated(
        _counted(), "dataset", StringValue(value="pfal3D7_Sexual_Stage_rnaSeq")
    )

    assert (restated.resolved_params["dataset"], restated.result_count) == (
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
        resolved_params={
            "dataset": StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq")
        },
    )
    spec = OperationalSpec(
        criteria=[_counted(), option],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_expression")
        ),
    )

    (carrier,) = fold_option_criteria(spec).spec.criteria

    assert (carrier.resolved_params["dataset"], carrier.result_count) == (
        StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq"),
        None,
    )
