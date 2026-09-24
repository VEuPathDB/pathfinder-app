"""A study step whose kind was never read is read when VERIFY asks for it.

A catalog that failed at the turn entry, or a search changed within the turn,
leaves a step with a document and no kind; the check reads it then.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
)

from pathfinder.ai.lead import pre_turn
from pathfinder.ai.tools.standalone.strategy_graph import (
    StrategySummaryResponse,
    StudyStepCheck,
    check_study_step,
    get_strategy,
)
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.persistence.models import PersistedStrategyGraph
from pathfinder.services.eda.analysis_kinds import read_the_unread_kinds
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.tests._support.analysis_catalog import (
    UNREADABLE_SEARCH,
    serve_the_catalog,
)
from pathfinder.tests._support.run_context import turn_runtime
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead._analysis_thread import document
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_WORDS = "Genes higher in 24h than in 18h (DESeq, |effect| >= 1, p <= 0.05)"


def _session(search_name: str) -> StrategySession:
    """A session holding one step that carries a document and no kind."""
    graph = StrategyGraph("g1", "DE", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(
        flatten_tree(
            StrategyStepNode(
                id="step_de",
                search_name=search_name,
                parameters={
                    EDA_DATASET_ID_PARAM: StringValue(value="DS_e973eadd57"),
                    EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
                },
            )
        )
    )
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    return session


async def test_an_unread_compute_step_is_read_and_answers_its_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = serve_the_catalog(monkeypatch)
    session = _session(COMPUTE_QUERY)

    answer = await check_study_step(
        agent_run_context(strategy_session=session), "step_de"
    )

    check = returned(answer, StudyStepCheck)
    assert check.thresholds is not None
    assert (check.thresholds.significance_threshold, check.method) == (0.05, "DESeq")
    assert read == [COMPUTE_QUERY]
    assert session.graph is not None
    assert session.graph.words.analysis_kinds == {
        "step_de": StampedKind(search_name=COMPUTE_QUERY, kind=AnalysisKind.COMPUTE)
    }


async def test_a_step_the_catalog_cannot_read_is_named_as_unread_not_as_no_study(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_catalog(monkeypatch)

    answer = await check_study_step(
        agent_run_context(strategy_session=_session(UNREADABLE_SEARCH)), "step_de"
    )

    summary = str(summary_of(answer).data["summary"])
    assert summary == "The site did not say how step step_de reads its analysis"
    assert "not a study step" not in str(answer.return_value)
    assert (
        "set success from the other checks and name this step in caveats as a "
        "pending check"
    ) in str(answer.return_value)


async def test_the_strategy_read_states_an_unread_step_by_what_it_selects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_catalog(monkeypatch)

    answer = await get_strategy(
        agent_run_context(strategy_session=_session(COMPUTE_QUERY))
    )

    summary = returned(answer, StrategySummaryResponse)
    assert (summary.analyses, summary.unread_analyses) == ({"step_de": _WORDS}, [])


@pytest.mark.parametrize("summary_only", [True, False])
async def test_the_strategy_read_names_a_step_the_site_cannot_read_as_pending(
    monkeypatch: pytest.MonkeyPatch, summary_only: bool
) -> None:
    """VERIFY finds study steps through this read, so an unread one is listed."""
    serve_the_catalog(monkeypatch)

    answer = await get_strategy(
        agent_run_context(strategy_session=_session(UNREADABLE_SEARCH)),
        summary_only=summary_only,
    )

    dumped = returned(answer, StrategySummaryResponse).model_dump(by_alias=True)
    assert (dumped["analyses"], dumped["unreadAnalyses"]) == ({}, ["step_de"])


async def test_a_search_the_site_cannot_read_is_read_once_a_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A site that is down is asked once a turn, and again by the next turn,
    which builds its own graph from the stored strategy."""
    read = serve_the_catalog(monkeypatch)
    session = _session(UNREADABLE_SEARCH)
    ctx = agent_run_context(strategy_session=session)

    await get_strategy(ctx)
    await check_study_step(ctx, "step_de")
    in_the_turn = list(read)
    stored = session.graph
    assert stored is not None
    next_turn = build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id="g1", name="DE", strategy_ast=stored.to_strategy_ast()
        ),
    )
    await pre_turn._stamp_the_analysis_kinds(turn_runtime(strategy_session=next_turn))

    assert (in_the_turn, read) == (
        [UNREADABLE_SEARCH],
        [UNREADABLE_SEARCH, UNREADABLE_SEARCH],
    )


async def test_the_site_read_and_the_entry_stamp_ask_a_failing_search_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn entry's site read stamps the graph the entry stamp then reads."""
    read = serve_the_catalog(monkeypatch)
    session = _session(UNREADABLE_SEARCH)
    stored = session.graph
    assert stored is not None

    await read_the_unread_kinds(site_id="plasmodb", graph=stored)
    await pre_turn._stamp_the_analysis_kinds(turn_runtime(strategy_session=session))

    assert read == [UNREADABLE_SEARCH]
