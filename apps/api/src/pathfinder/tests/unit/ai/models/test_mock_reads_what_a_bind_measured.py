"""The mock reads what a bind measured: FRAME's summary names each measurement
the binding returned."""

from __future__ import annotations

from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    CriterionSpec,
    SpecPlan,
    frame_result,
    leaf,
)

_CLAUSE = (
    "Minimum expression percentile at the site's default of 80: 1,087 genes; "
    "at 0: 5,318"
)


def test_the_frame_summary_names_each_measurement_of_its_bindings() -> None:
    crit = CriterionSpec(
        criterion_id="c_expr", text="expressed", search_name="GenesByRNASeq"
    )
    spec = SpecPlan(title="expressed genes", criteria=(crit,), structure=leaf(crit))
    bound = CriterionReply(
        criterion_id="c_expr",
        search_name="GenesByRNASeq",
        resolved_params={"min_expression_percentile": "80"},
        measurements=[_CLAUSE],
    )

    summary = frame_result(spec, [bound])["summary"]

    assert summary == f"Framed 1 criterion(s) for expressed genes. {_CLAUSE}."
