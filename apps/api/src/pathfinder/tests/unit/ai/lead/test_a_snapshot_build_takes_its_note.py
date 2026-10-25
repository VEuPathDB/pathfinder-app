from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from veupathdb.domain.parameters import InputDatasetValue, MultiPickValue
from veupathdb.domain.strategy import CombineOp, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, sub_agent_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.computed_groups import SNAPSHOT_NOTE
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation, UpdateStrategyMetaOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_tree import build_step_tree, renumber_criteria
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.computed_comparison import PATTERN, held_comparison
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_DATASET = "202394260"
_MINE = "Groups for the grant figure."
_WORDS = "groups with more proteins per genome in the left set"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal=_WORDS,
        criteria=[
            Criterion(
                id="c_groups",
                text=_WORDS,
                search_name="GroupsByNameList",
                record_class="group",
                resolved_params={
                    "group_names": BoundValue(
                        value=InputDatasetValue(dataset_id=_DATASET), source="chosen"
                    )
                },
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_groups")
        ),
    )


def _drop(_part: object) -> None:
    return None


async def _described(
    monkeypatch: pytest.MonkeyPatch, saved: str, described: str | None
) -> list[str | None]:
    sent: list[str | None] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        sent.append(kwargs["description"])
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    monkeypatch.setattr(sub_agent_dispatch, "get_stream_writer", lambda: _drop)
    held = held_comparison(PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": saved}
    )
    state = pipeline_state(
        "orthomcl",
        user_prompt=_WORDS,
        domain=StrategyDomainState(
            operational_spec=_spec(), computed_comparisons={held.handle: held}
        ),
    )
    session = StrategySession(site_id="orthomcl")
    session.graph = StrategyGraph("g1", "Groups", "orthomcl")
    session.graph.description = described
    await build_strategy(run_context_for(lead_deps(state, strategy_session=session)))
    return sent


@pytest.mark.parametrize(
    ("saved", "described", "sent"),
    [
        (_DATASET, None, SNAPSHOT_NOTE),
        (_DATASET, _MINE, f"{_MINE} {SNAPSHOT_NOTE}"),
        ("1", _MINE, _MINE),
        ("1", None, None),
    ],
)
async def test_a_build_writes_the_note_beside_the_description(
    monkeypatch: pytest.MonkeyPatch,
    saved: str,
    described: str | None,
    sent: str | None,
) -> None:
    assert await _described(monkeypatch, saved, described) == [sent]


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _built() -> tuple[OperationalSpec, StrategySession]:
    taxon = Criterion(
        id="c_taxon",
        text="genes of one organism",
        search_name="GenesByTaxon",
        role="seed",
        resolved_params=bound({"organism": MultiPickValue(values=["organism A"])}),
    )
    spec = OperationalSpec(
        goal=_WORDS, criteria=[taxon], structure=SpecStructure(root=_leaf("c_taxon"))
    )
    tree = build_step_tree(spec)
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="Groups", site_id="orthomcl")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


async def test_an_edit_that_binds_a_saved_comparison_notes_the_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, session = _built()
    after = before.model_copy(deep=True)
    after.criteria.append(_spec().criteria[0])
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[_leaf(before.criteria[0].id), _leaf("c_groups")],
        )
    )
    held = held_comparison(PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": _DATASET}
    )
    state = pipeline_state(
        "orthomcl",
        user_prompt="keep only the computed groups",
        domain=StrategyDomainState(
            operational_spec=before.model_copy(deep=True),
            computed_comparisons={held.handle: held},
        ),
    )
    state.domain.spec_before_turn = before
    batches: list[list[GraphOperation]] = []

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_apply(**kwargs: Any) -> CommitResult:
        batches.append(kwargs["ops"])
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_apply)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: _drop)

    await run_edit(
        deps=lead_deps(state, strategy_session=session),
        parent_tool_call_id="t1",
        reason="computed groups",
    )

    [ops] = batches
    assert ops[-1] == UpdateStrategyMetaOp(description=SNAPSHOT_NOTE)
