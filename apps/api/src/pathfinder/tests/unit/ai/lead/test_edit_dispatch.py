"""The edit dispatch: misrouted edits, and the snapshot it emits."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, flatten_tree
from veupathdb.errors import ValidationError

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState, TurnMarkers
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        criteria=[
            Criterion(
                id="step_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_go"),
                ],
            )
        ),
    )


async def test_an_edit_on_a_thread_with_no_strategy_keeps_the_framed_spec() -> None:
    """A misrouted edit is a retry, and it destroys nothing the turn framed."""
    deps = lead_deps(
        pipeline_state(
            user_prompt="use P. vivax for the GO criterion",
            domain=StrategyDomainState(operational_spec=_spec()),
        ),
    )
    deps.state.domain.spec_before_turn = None

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason="edit it")

    assert "frame_problem" in str(excinfo.value)
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {"step_text", "step_go"}


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: calls.append)
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("graph-1", "Heat shock", "plasmodb"))
    edit_dispatch._emit_graph_snapshot(
        AgentDeps(
            site_id="plasmodb", strategy_session=session, turn_markers=TurnMarkers()
        )
    )
    return calls


def test_the_snapshot_reaches_the_writer_under_the_chunk_key(
    emitted: list[dict[str, Any]],
) -> None:
    assert [call["chunk"]["type"] for call in emitted] == ["data-graph-snapshot"]


def test_the_envelope_omits_the_keys_the_chunk_leaves_unset(
    emitted: list[dict[str, Any]],
) -> None:
    """``DataChunk`` declares optional ``id`` and ``transient`` keys, and every
    emitted chunk is persisted verbatim."""
    assert sorted(emitted[0]["chunk"]) == ["data", "type"]


def test_the_snapshot_payload_names_the_graph(
    emitted: list[dict[str, Any]],
) -> None:
    assert emitted[0]["chunk"]["data"]["strategyId"] == "graph-1"


_SEARCH = "GenesByRNASeqEvidence"
_DEFAULT_DATASET = "all_rnaseq"
_SEXUAL_STAGE = "pfal3D7_Sexual_Stage_rnaSeq"
_TIMECOURSE = "pfal3D7_Gametocyte_Timecourse_rnaSeq"


def _carrier(criterion_id: str = "gametocyte_expression") -> Criterion:
    return Criterion(
        id=criterion_id,
        text="upregulated in gametocytes",
        search_name=_SEARCH,
        resolved_params={
            "organism": MultiPickValue(values=["Pf3D7"]),
            "dataset": StringValue(value=_DEFAULT_DATASET),
        },
        defaulted_params=["dataset"],
    )


def _option(search_name: str = _SEARCH) -> Criterion:
    return Criterion(
        id="sexual_stage_option",
        text="use the sexual stage dataset",
        search_name=search_name,
        resolved_params={"dataset": StringValue(value=_SEXUAL_STAGE)},
    )


def _built() -> tuple[OperationalSpec, StrategySession]:
    """The strategy on screen: one step running the search with its default."""
    spec = OperationalSpec(
        goal="genes upregulated in gametocytes",
        criteria=[_carrier()],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="gametocyte_expression")
        ),
    )
    tree = build_step_tree(spec)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="gametocytes", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


class EditRun:
    """One ``run_edit`` over a stored spec, with the operations it committed."""

    def __init__(self, deps: LeadDeps, operations: list[GraphOperation]) -> None:
        self.deps = deps
        self.operations = operations

    @property
    def stored_criteria(self) -> list[Criterion]:
        spec = self.deps.state.domain.operational_spec
        return list(spec.criteria) if spec is not None else []

    def dumped(self) -> list[dict[str, Any]]:
        return [op.model_dump(by_alias=True, mode="json") for op in self.operations]


def _edit_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: OperationalSpec,
    after: OperationalSpec,
    session: StrategySession,
    commit_result: CommitResult | None = None,
) -> EditRun:
    """Drive ``run_edit`` with FRAME and the commit replaced by captures."""
    committed: list[GraphOperation] = []
    state = pipeline_state(
        user_prompt="use the sexual stage dataset",
        domain=StrategyDomainState(operational_spec=after),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_commit(**kwargs: Any) -> CommitResult:
        committed.extend(kwargs["ops"])
        if commit_result is not None:
            return commit_result
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    return EditRun(deps, committed)


async def test_a_restated_option_is_pushed_as_a_step_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edit states the option on the step that runs its search."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    step_id = before.criteria[0].id
    assert run.dumped() == [
        {
            "kind": "updateStepParams",
            "stepId": step_id,
            "parameters": {
                "organism": {"type": "multi-pick-vocabulary", "values": ["Pf3D7"]},
                "dataset": {"type": "string", "value": _SEXUAL_STAGE},
            },
        }
    ]


async def test_the_spec_stored_after_an_edit_is_folded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build and an edit leave the thread the same spec for one strategy."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    (stored,) = run.stored_criteria
    assert stored.resolved_params["dataset"] == StringValue(value=_SEXUAL_STAGE)
    assert [a.reason for a in stored.assumptions] == ["use the sexual stage dataset"]


async def test_an_option_two_steps_could_carry_refuses_the_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spec this turn wrote states the option the build's way or not at all."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_carrier("asexual_expression"))
    after.criteria.append(_option())
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id=before.criteria[0].id),
                StructureNode(kind="leaf", criterion_id="asexual_expression"),
            ],
        )
    )
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    assert "sexual_stage_option" in str(excinfo.value)
    assert run.operations == []


async def test_a_stored_option_no_step_carries_does_not_refuse_the_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stored spec is what an earlier turn left, so the edit that fixes it runs."""
    before, session = _built()
    before.criteria.append(_option("GenesByTaxon"))
    after = OperationalSpec(
        goal=before.goal,
        criteria=[before.criteria[0].model_copy(deep=True)],
        structure=before.structure,
    )
    after.criteria[0].resolved_params["dataset"] = StringValue(value=_SEXUAL_STAGE)
    after.criteria[0].defaulted_params = []
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    assert [op.kind for op in run.operations] == ["updateStepParams"]


def _timecourse_option() -> Criterion:
    return Criterion(
        id="timecourse_option",
        text="use the gametocyte timecourse dataset",
        search_name=_SEARCH,
        resolved_params={"dataset": StringValue(value=_TIMECOURSE)},
    )


async def test_two_options_that_state_one_value_push_one_step_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second statement of a value the fold carried changes nothing more."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    second = _option()
    second.id = "sexual_stage_restated"
    after.criteria.append(second)
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    assert run.dumped() == [
        {
            "kind": "updateStepParams",
            "stepId": before.criteria[0].id,
            "parameters": {
                "organism": {"type": "multi-pick-vocabulary", "values": ["Pf3D7"]},
                "dataset": {"type": "string", "value": _SEXUAL_STAGE},
            },
        }
    ]


async def test_an_option_that_contradicts_another_refuses_the_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two datasets for one step is a contradiction the edit cannot resolve."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    after.criteria.append(_timecourse_option())
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    message = str(excinfo.value)
    assert "timecourse_option" in message
    assert _SEXUAL_STAGE in message
    assert _TIMECOURSE in message
    assert run.operations == []


def _refused_commit(*, status: int | None) -> CommitResult:
    return CommitResult(
        description="edited",
        failures=[
            StepPushFailure(
                step_id="step_1",
                search_name=_SEARCH,
                error="dataset: Invalid value 'pfal3D7_Sexual_Stage_rnaSeq'",
                wdk_status=status,
            )
        ],
    )


async def test_an_edit_wdk_refused_is_retried_with_wdks_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal of the values is a retry, because other values can pass."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    run = _edit_run(
        monkeypatch,
        before=before,
        after=after,
        session=session,
        commit_result=_refused_commit(status=422),
    )

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    assert "dataset: Invalid value" in str(excinfo.value)


async def test_an_unreachable_site_leaves_no_success_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer a retry cannot mend is the delta's description."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    run = _edit_run(
        monkeypatch,
        before=before,
        after=after,
        session=session,
        commit_result=_refused_commit(status=None),
    )

    delta = await run_edit(
        deps=run.deps, parent_tool_call_id="t1", reason="new dataset"
    )

    assert isinstance(delta, EditDelta)
    assert delta.description != "edited"
    assert "dataset: Invalid value" in delta.description
    assert delta.failed_step_ids == ["step_1"]


async def test_a_value_the_catalog_turns_down_ends_the_edit_with_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The commit canonicalizes what it writes, so its refusal reaches the Lead."""
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_option())
    run = _edit_run(monkeypatch, before=before, after=after, session=session)

    async def _refuse(**_kwargs: Any) -> CommitResult:
        raise ValidationError(
            title="Invalid parameter value",
            detail="Parameter 'dataset' does not accept 'NotARealDataset'.",
        )

    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _refuse)

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=run.deps, parent_tool_call_id="t1", reason="new dataset")

    assert "NotARealDataset" in str(excinfo.value)
    assert run.deps.state.domain.operational_spec == before
