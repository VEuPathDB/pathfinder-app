from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from strategist.ai.lead import score_counts
from strategist.ai.lead.score_counts import record_score_counts
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.comparison_facts import ComparedVariant, ComparisonFact
from strategist.tests._support.column_reads import ColumnSite, serve_columns
from strategist.tests._support.recorded_columns import column_catalog
from strategist.tests._support.run_context import lead_run_context
from strategist.tests._support.step_tally_site import TallySite, ToolServer, serve
from strategist.tests.unit.ai.lead._site_verdict import (
    UNANSWERED_DIGEST,
    serve_the_site,
    verify,
)
from strategist.tests.unit.ai.lead.test_a_second_organism_fails_the_verdict import (
    _EXPORTED,
    _exported_deps,
    _exported_details,
    _organisms,
)
from strategist.tests.unit.ai.tools._strategy_edit_stubs import session_with

_ROOT = 9003


def _deps(weight: int | None) -> LeadDeps:
    root = StrategyStepNode(
        id="union",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="a", search_name="GenesByTaxon", wdk_weight=weight
        ),
        secondary_input=StrategyStepNode(
            id="b", search_name="GenesByTaxon", wdk_weight=weight
        ),
    )
    session = session_with(root, {"a": 9001, "b": 9002, "union": _ROOT})
    graph = session.get_graph(None)
    assert graph is not None
    for step in graph.steps.values():
        step.record_class = "transcript"
    return lead_run_context(strategy_session=session).deps


def _serve(
    monkeypatch: pytest.MonkeyPatch, counts: dict[int, int]
) -> list[tuple[str, int, str | None]]:
    asked: list[tuple[str, int, str | None]] = []

    async def _counted(
        site_id: str, wdk_step_id: int, record_type: str | None
    ) -> dict[int, int]:
        asked.append((site_id, wdk_step_id, record_type))
        return counts

    monkeypatch.setattr(score_counts, "count_weights", _counted)
    return asked


async def test_a_ranked_result_shows_its_genes_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, {1: 7, 2: 4})
    deps = _deps(1)

    await record_score_counts(deps)

    assert asked == [("plasmodb", _ROOT, "transcript")]
    assert deps.state.turn_markers.comparisons == [
        ComparisonFact(
            variants=[
                ComparedVariant(label="Score 2 of 2", gene_count=4),
                ComparedVariant(label="Score 1 of 2", gene_count=7),
            ],
            on_its_card=False,
        )
    ]


async def test_a_large_ranked_result_is_counted_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, {1: 3_100, 2: 1_900, 3: 291})
    deps = _deps(1)

    await record_score_counts(deps)

    assert [
        variant.gene_count
        for variant in deps.state.turn_markers.comparisons[0].variants
    ] == [291, 1_900, 3_100]


async def test_an_unweighted_result_is_not_counted_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, {0: 11})
    deps = _deps(None)

    await record_score_counts(deps)

    assert (asked, deps.state.turn_markers.comparisons) == ([], [])


@pytest.mark.usefixtures("collector")
async def test_the_check_counts_a_ranked_result_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _exported_details(), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    organisms = ToolServer(counts=_organisms(("<i>Plasmodium falciparum</i> 3D7", 3)))
    serve(monkeypatch, TallySite(column_catalog(), step_count=4200), organisms)
    asked = _serve(monkeypatch, {1: 3})
    deps = _exported_deps()
    graph = deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    graph.steps["c_text"].wdk_weight = 1

    await verify(monkeypatch, deps, UNANSWERED_DIGEST)

    assert asked == [("plasmodb", _EXPORTED, "transcript")]
    assert deps.state.turn_markers.comparisons[-1].variants == [
        ComparedVariant(label="Score 1 of 1", gene_count=3)
    ]
