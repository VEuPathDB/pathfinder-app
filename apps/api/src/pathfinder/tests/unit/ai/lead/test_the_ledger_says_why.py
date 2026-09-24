"""The Lead's ledger prints why each criterion runs its search, so a later
"why that search?" is answered from the record."""

from __future__ import annotations

from pathfinder.ai.lead.ledger_render import render_frame_full
from pathfinder.ai.lead.ledger_sections import FrameSection
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.step_rationale import ComparedSearch, SearchRationale
from pathfinder.tests.unit.domain.strategy._analysis import WORDS, analysed

_CHOSEN = SearchRationale(
    search_name="GenesByExportPrediction",
    basis="nearest",
    term="GPI anchor",
    reason="no search states a GPI anchor; Exported Protein scored nearest",
    similarity=0.44,
    compared=[
        ComparedSearch(
            name="GenesByText", display_name="Gene Text Search", similarity=0.41
        )
    ],
    tool_call_id="call_gpi",
)


def _why_lines(*criteria: Criterion) -> list[str]:
    rendered = render_frame_full(
        FrameSection(spec=OperationalSpec(goal="g", criteria=list(criteria)))
    )
    return [line for line in rendered.splitlines() if line.startswith("    WHY ")]


def test_a_chosen_search_prints_its_reason_and_what_it_was_chosen_over() -> None:
    gpi = Criterion(
        id="c_gpi",
        text="genes with a predicted GPI anchor",
        search_name="GenesByExportPrediction",
        rationale=_CHOSEN,
    )

    assert _why_lines(gpi) == [
        (
            "    WHY no search states a GPI anchor; Exported Protein scored nearest "
            "(over Gene Text Search 0.41)"
        )
    ]


def test_an_analysis_prints_the_compute_its_document_holds() -> None:
    assert _why_lines(analysed()) == [f"    WHY {WORDS}"]


def test_a_criterion_with_no_reason_prints_none() -> None:
    bare = Criterion(id="c_text", text="kinases", search_name="GenesByText")

    assert _why_lines(bare) == []
