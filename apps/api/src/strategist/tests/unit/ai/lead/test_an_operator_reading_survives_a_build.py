from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    walk,
)

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import sub_agent_dispatch
from strategist.ai.lead.dispatch_context import (
    agent_deps_for,
    record_the_spec_the_dispatch_found,
)
from strategist.ai.lead.sub_agent_dispatch import MintedSpec, build_the_minted
from strategist.domain.strategy.data_marks import DataMarks
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operator_reading import read_operators
from strategist.domain.strategy.operator_reads import OperatorReading
from strategist.domain.strategy.saved_strategy_ref import SavedStrategyRef
from strategist.domain.strategy.spec_tree import build_step_tree
from strategist.services.strategies import spec_build
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    Env,
    new_thread,
)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _read_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        criteria=[
            Criterion(id="c_sp", text="sp", search_name="GenesWithSignalPeptide"),
            Criterion(id="c_tm", text="tm", search_name="GenesByTransmembraneDomains"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[_leaf("c_sp"), _leaf("c_tm")],
            )
        ),
        operator_reads=[
            OperatorReading(
                criteria=["c_sp", "c_tm"],
                built=CombineOp.UNION,
                read="disagrees",
                read_operator=CombineOp.INTERSECT,
                confidence=0.63,
            )
        ],
    )


async def _nothing(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _no_marks(*_args: Any, **_kwargs: Any) -> DataMarks:
    return DataMarks()


async def test_an_operator_reading_is_held_after_a_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Env(monkeypatch)
    monkeypatch.setattr(
        sub_agent_dispatch, "get_stream_writer", lambda: lambda _part: None
    )
    monkeypatch.setattr(sub_agent_dispatch, "read_data_marks", _no_marks)
    monkeypatch.setattr(
        sub_agent_dispatch, "import_gene_set_for_conversation", _nothing
    )
    monkeypatch.setattr(spec_build, "persist_strategy_ast_to_conversation", _nothing)
    monkeypatch.setattr(spec_build, "defer_the_gene_set_refresh", _nothing)
    spec = _read_spec()
    state = pipeline_state(
        user_prompt="build it", domain=StrategyDomainState(operational_spec=spec)
    )
    deps = lead_deps(state, strategy_session=new_thread().strategy_session)

    await build_the_minted(
        deps, MintedSpec(spec=spec, root=build_step_tree(spec)), call_id="call_build"
    )
    record_the_spec_the_dispatch_found(deps, resume=None)
    held = deps.state.domain.operational_spec

    assert held is not None
    assert (read_operators(held), held.asks_an_operator) == (
        frozenset({CombineOp.INTERSECT}),
        True,
    )
    assert agent_deps_for(deps, call_id="call_next").agent_state.read_operators == (
        frozenset({CombineOp.INTERSECT})
    )


def _two_searches() -> OperationalSpec:
    return _read_spec().model_copy(update={"operator_reads": []})


def _leaf_and_transform_ids(root: StrategyStepNode) -> list[str]:
    return [n.id for n in walk(root) if n.operator is None]


def test_every_leaf_takes_its_criterions_id() -> None:
    assert _leaf_and_transform_ids(build_step_tree(_two_searches())) == [
        "c_sp",
        "c_tm",
    ]


def test_a_second_build_of_one_spec_mints_the_same_ids() -> None:
    spec = _two_searches()

    assert _leaf_and_transform_ids(build_step_tree(spec)) == _leaf_and_transform_ids(
        build_step_tree(spec)
    )


def test_a_transform_takes_its_criterions_id() -> None:
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(id="c_text", text="kinase", search_name="GenesByText"),
            Criterion(id="c_orth", text="orthologs", search_name="GenesByOrthologs"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform", criterion_id="c_orth", inputs=[_leaf("c_text")]
            )
        ),
    )

    root = build_step_tree(spec)

    assert (root.id, root.primary_input and root.primary_input.id) == (
        "c_orth",
        "c_text",
    )


def test_a_saved_reference_roots_under_its_criterions_id() -> None:
    saved = SavedStrategyRef(
        conversation_id="9bd3a584-0000-4000-8000-000000000001",
        name="Pf protease union",
        wdk_strategy_id=330534203,
        step_count=3,
        subtree=StrategyStepNode(
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(search_name="GenesByText"),
            secondary_input=StrategyStepNode(search_name="GenesByGoTerm"),
        ),
    )
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(
                id="c_saved", text="my proteases", role="seed", saved_strategy_ref=saved
            )
        ],
        structure=SpecStructure(root=_leaf("c_saved")),
    )

    assert build_step_tree(spec).id == "c_saved"
