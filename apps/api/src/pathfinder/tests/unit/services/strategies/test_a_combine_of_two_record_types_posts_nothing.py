from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.operations import ReplaceSubtreeOp
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.spec_build import build_strategy_from_spec
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    session_with,
)

_REFUSAL = (
    "The INTERSECT of step_protein (Proteins) and step_mammals (Ortholog Groups) "
    "joins two record types. WDK combines only steps of one record type, so the "
    "site refuses this combine. Transform Proteins to Groups (GroupsFromSequences) "
    "maps Proteins to Ortholog Groups: put it over step_protein. Transform Groups "
    "to Proteins (FromGroups) maps Ortholog Groups to Proteins: put it over "
    "step_mammals."
)


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = install_stub_api(monkeypatch)
    serve_orthomcl_record_classes(monkeypatch)
    return api


def _step(
    step_id: str, search_name: str, source: StrategyStepNode | None = None
) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name, primary_input=source)


def _protein() -> StrategyStepNode:
    return _step("step_protein", "ByIdList")


def _mammals() -> StrategyStepNode:
    return _step("step_mammals", "GroupsByPhyleticPattern")


def _empty_session() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "Trypanothione reductase", "orthomcl")
    graph.record_type = "group"
    session.graph = graph
    return session


async def _build(session: StrategySession, root: StrategyStepNode) -> int | None:
    outcome = await build_strategy_from_spec(
        deps=StrategyMutationContext(site_id="orthomcl", strategy_session=session),
        root=root,
    )
    return outcome.wdk_strategy_id


async def test_a_build_of_a_protein_step_and_a_group_step_posts_nothing(
    api: StubAPI,
) -> None:
    session = _empty_session()

    with pytest.raises(ApplyError) as refused:
        await _build(session, combine("step_join", _protein(), _mammals()))

    assert session.graph is not None
    assert (str(refused.value), api.calls, session.graph.steps) == (_REFUSAL, [], {})


async def test_a_build_over_the_proteins_groups_posts_every_step(
    api: StubAPI,
) -> None:
    groups = _step("step_groups", "GroupsFromSequences", _protein())

    built = await _build(_empty_session(), combine("step_join", groups, _mammals()))

    assert (built, sorted(call.name for call in api.calls)) == (
        42,
        [
            "create_combined_step",
            "create_step",
            "create_step",
            "create_transform_step",
        ],
    )


async def test_a_build_of_two_protein_steps_posts_the_combine(api: StubAPI) -> None:
    other = _step("step_other", "ByIdList")

    built = await _build(_empty_session(), combine("step_join", _protein(), other))

    assert (built, sorted(call.name for call in api.calls)) == (
        42,
        ["create_combined_step", "create_step", "create_step"],
    )


async def test_an_edit_that_joins_a_group_step_to_proteins_posts_nothing(
    api: StubAPI,
) -> None:
    session = session_with(_protein(), {"step_protein": 227284890})
    held = dict(session.graph.steps) if session.graph is not None else {}

    with pytest.raises(ApplyError) as refused:
        await apply_and_commit(
            deps=StrategyMutationContext(site_id="orthomcl", strategy_session=session),
            op=ReplaceSubtreeOp(
                step_id="step_protein",
                subtree=combine(
                    "step_join", _protein(), _mammals(), CombineOp.INTERSECT
                ),
            ),
        )

    assert session.graph is not None
    assert (str(refused.value), api.calls, session.graph.steps) == (
        _REFUSAL,
        [],
        held,
    )
