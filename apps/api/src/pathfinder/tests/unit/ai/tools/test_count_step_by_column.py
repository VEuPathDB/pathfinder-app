"""The Lead counts a built step's records by a column: the step is read under its
own record type, the card links the step on the site, and a step the strategy
does not hold or a column the site cannot count goes back to the model."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.tools.standalone import step_tally
from pathfinder.ai.tools.standalone.step_tally import count_step_by_column
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment.column_tally import (
    ColumnTally,
    ColumnTallyRefusedError,
)
from pathfinder.services.experiment.step_tally import CountedStep
from pathfinder.services.experiment.tally_rows import TallyRow
from pathfinder.services.strategies.result_list import result_list_url
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context

_STRATEGY = 1188
_GROUPS_STEP = 227284070
_PROTEINS_STEP = 227284080


def _singletons_then_proteins() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "the proteins of the singleton groups", "orthomcl")
    graph.record_type = "sequence"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="proteins",
            search_name="FromGroups",
            primary_input=StrategyStepNode(
                id="groups", search_name="GroupsBySequenceCount"
            ),
        )
    )
    graph.steps["groups"].record_class = "group"
    graph.steps["proteins"].record_class = "sequence"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"groups": _GROUPS_STEP, "proteins": _PROTEINS_STEP},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(
            step_id=_PROTEINS_STEP, primary_input=WDKStepTree(step_id=_GROUPS_STEP)
        ),
    )
    return session


class _Ran:
    def __init__(self) -> None:
        self.asked: list[tuple[CountedStep, str]] = []
        self.tops: list[int] = []
        self.returned: list[ColumnTally] = []

    async def __call__(self, step: CountedStep, column: str, top: int) -> ColumnTally:
        self.asked.append((step, column))
        self.tops.append(top)
        if column == "length":
            msg = "protein records cannot be counted by length."
            raise ColumnTallyRefusedError(msg)
        if column == "taxon_name":
            msg = "Request failed after retries: "
            raise WDKError(msg, status=504)
        tally = ColumnTally(
            id="tally_5e6f7a8b",
            title="Proteins by Taxon Code",
            search_name=step.search_name,
            record_type=step.record_type,
            record_noun=step.record_noun,
            column=column,
            column_label="Taxon Code",
            total=523795,
            distinct=840,
            rows=[
                TallyRow(value="bpli", count=18260, label="Brachionus plicatilis"),
                TallyRow(value="osat", count=9365, label="Oryza sativa Japonica Group"),
            ],
            site_id=step.site_id,
            step_url=step.step_url,
        )
        self.returned.append(tally)
        return tally


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    fake = _Ran()
    monkeypatch.setattr(step_tally, "run_step_tally", fake)
    return fake


async def test_a_transform_step_is_counted_and_linked_on_the_site(ran: _Ran) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    result = await count_step_by_column(ctx, _PROTEINS_STEP, "abbreviation")

    step_url = result_list_url("orthomcl", _STRATEGY, _PROTEINS_STEP)
    assert step_url.endswith(
        f"/app/workspace/strategies/{_STRATEGY}/{_PROTEINS_STEP}/summary:_default"
    )
    assert ran.asked == [
        (
            CountedStep(
                site_id="orthomcl",
                wdk_step_id=_PROTEINS_STEP,
                record_type="sequence",
                search_name="FromGroups",
                record_noun="protein",
                step_url=step_url,
            ),
            "abbreviation",
        )
    ]
    assert ran.tops == [20]
    tally = ran.returned[0].model_copy(update={"result_step_id": _PROTEINS_STEP})
    assert ctx.deps.state.turn_markers.tallies == [tally.fact()]
    assert [r.label for r in ctx.deps.state.turn_markers.tallies[0].rows] == [
        "Brachionus plicatilis",
        "Oryza sativa Japonica Group",
    ]
    chunks = [
        c
        for c in result.metadata or []
        if isinstance(c, DataChunk) and c.type == "data-column-tally"
    ]
    assert [c.data for c in chunks] == [tally.model_dump(by_alias=True, mode="json")]
    assert chunks[0].data["stepUrl"] == step_url


async def test_a_step_the_strategy_does_not_hold_goes_back_to_the_model(
    ran: _Ran,
) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    with pytest.raises(ModelRetry) as refused:
        await count_step_by_column(ctx, 1, "abbreviation")

    assert str(refused.value) == (
        "Step 1 is not a step of this strategy. Its built steps: "
        f"{_GROUPS_STEP}, {_PROTEINS_STEP}."
    )
    assert ran.asked == []


async def test_a_strategy_with_no_built_step_says_so(ran: _Ran) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=StrategySession(site_id="orthomcl")
    )

    with pytest.raises(ModelRetry) as refused:
        await count_step_by_column(ctx, 1, "abbreviation")

    assert str(refused.value) == (
        "Step 1 is not a step of this strategy. This strategy has no built step yet."
    )
    assert ran.asked == []


async def test_the_count_and_the_link_name_the_strategys_site(ran: _Ran) -> None:
    ctx = lead_run_context(
        site_id="plasmodb", strategy_session=_singletons_then_proteins()
    )

    await count_step_by_column(ctx, _PROTEINS_STEP, "abbreviation")

    ((step, _),) = ran.asked
    assert (step.site_id, step.step_url) == (
        "orthomcl",
        result_list_url("orthomcl", _STRATEGY, _PROTEINS_STEP),
    )


async def test_a_server_error_fails_the_count_and_refuses_no_column(
    ran: _Ran,
) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    with pytest.raises(WDKError):
        await count_step_by_column(ctx, _PROTEINS_STEP, "taxon_name")
    await count_step_by_column(ctx, _PROTEINS_STEP, "abbreviation")

    assert [step.refused for step, _ in ran.asked] == [frozenset(), frozenset()]


async def test_a_column_the_site_cannot_count_goes_back_to_the_model(
    ran: _Ran,
) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    with pytest.raises(ModelRetry, match="cannot be counted by length"):
        await count_step_by_column(ctx, _PROTEINS_STEP, "length")

    assert ctx.deps.state.turn_markers.tallies == []


async def test_a_refused_column_is_not_offered_again_on_that_step(ran: _Ran) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    with pytest.raises(ModelRetry):
        await count_step_by_column(ctx, _PROTEINS_STEP, "length")
    await count_step_by_column(ctx, _PROTEINS_STEP, "abbreviation")
    await count_step_by_column(ctx, _GROUPS_STEP, "abbreviation")

    assert [(step.wdk_step_id, step.refused) for step, _ in ran.asked] == [
        (_PROTEINS_STEP, frozenset()),
        (_PROTEINS_STEP, frozenset({"length"})),
        (_GROUPS_STEP, frozenset()),
    ]


def _transcripts() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "kinases", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id="kinases", search_name="GenesByText")
    )
    graph.steps["kinases"].record_class = "transcript"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"kinases": 441031663})
    return session


async def test_a_transcript_step_is_counted_in_transcripts(ran: _Ran) -> None:
    ctx = lead_run_context(site_id="plasmodb", strategy_session=_transcripts())

    await count_step_by_column(ctx, 441031663, "organism", top=5)

    ((step, column),) = ran.asked
    assert (step.record_type, step.record_noun, column, ran.tops) == (
        "transcript",
        "transcript",
        "organism",
        [5],
    )
    assert step.step_url is None


async def test_the_counts_are_lines_of_the_turns_facts(ran: _Ran) -> None:
    ctx = lead_run_context(
        site_id="orthomcl", strategy_session=_singletons_then_proteins()
    )

    await count_step_by_column(ctx, _PROTEINS_STEP, "abbreviation")

    [tally] = ctx.deps.state.turn_markers.tallies
    lines = tally.lines()
    assert (lines[1:3], "bpli: 18,260" in lines) == (
        ["In all: 523,795 proteins", "Values: 840"],
        True,
    )


def test_each_way_the_step_count_is_refused_keeps_a_retry() -> None:
    read_once = build_lead_toolset()
    assert isinstance(read_once, WrapperToolset)
    refusal_memory = read_once.wrapped
    assert isinstance(refusal_memory, WrapperToolset)
    base = refusal_memory.wrapped
    assert isinstance(base, FunctionToolset)

    assert base.tools["count_step_by_column"].max_retries == 6
