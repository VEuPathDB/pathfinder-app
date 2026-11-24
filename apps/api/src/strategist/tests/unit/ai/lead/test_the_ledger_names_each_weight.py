from __future__ import annotations

from strategist.ai.lead.ledger_render import render_frame_full
from strategist.ai.lead.ledger_sections import FrameSection
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec


def _weight_lines(*criteria: Criterion) -> list[str]:
    rendered = render_frame_full(
        FrameSection(spec=OperationalSpec(goal="g", criteria=list(criteria)))
    )
    return [
        line
        for line in rendered.splitlines()
        if line.startswith(("    SETTINGS ", "    RANKED"))
    ]


def test_a_weighted_criterion_says_what_its_weight_adds() -> None:
    lines = _weight_lines(
        Criterion(id="c_a", text="a", search_name="GenesByText", weight=2),
        Criterion(id="c_b", text="b", search_name="GenesByText"),
    )

    assert lines == [
        "    SETTINGS weight 2",
        (
            "    RANKED: a gene this search finds scores its weight more; the result "
            "is sorted by score, highest first"
        ),
    ]
