"""An analysis that cannot export rows sends the reader to its figures, which
show the counts, and never asks the reply to state them."""

from __future__ import annotations

from pathfinder.ai.tools.standalone._eda_guidance import opened_guidance


def test_a_study_with_no_gene_link_points_at_the_figures() -> None:
    guidance = opened_guidance(
        gene_problem="This study's samples link to no gene.", can_export=True
    )

    assert guidance == (
        "Call set_eda_filters with no filters to read the filter sheet, then "
        "again with the whole filter array. This study's samples link to no gene. "
        "This analysis cannot export rows into a strategy step; its figures show "
        "the counts and the distributions, and the reply says what they mean."
    )
