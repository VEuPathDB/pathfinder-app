from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.answered_strategy import the_changes_written_outside
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state, stated_spec_of
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import record_classes
from pathfinder.tests.unit.ai.lead.conftest import lead_runtime, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_LISTED = {
    "GroupsByPhyleticPattern": "group",
    "FromGroups": "sequence",
}


@pytest.fixture(autouse=True)
def _orthomcl_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(search_name: str) -> str | None:
            return _LISTED.get(search_name)

        return _listed_under

    async def _sheets(**_kwargs: Any) -> dict[str, list[ParameterInfo]]:
        return {}

    async def _marks(_site_id: str, _searches: Collection[str]) -> dict[str, str]:
        return {}

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    for module in (answered_strategy, pre_turn):
        monkeypatch.setattr(module, "sheet_params_for_searches", _sheets)
        monkeypatch.setattr(module, "organism_parameters", _marks)


def _pattern() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_groups",
        search_name="GroupsByPhyleticPattern",
        parameters={"phyletic_expression": StringValue(value="pfal>=1T AND tgon=0T")},
    )


def _proteins() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_proteins", search_name="FromGroups", primary_input=_pattern()
    )


def _graph(root: StrategyStepNode, record_type: str) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="groups", site_id="orthomcl")
    graph.record_type = record_type
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


async def test_a_hydrated_group_strategy_is_stated_on_the_group_class() -> None:
    spec = await stated_spec_of(
        StrategyAst(record_type="group", root=_pattern()),
        site_id="orthomcl",
        goal="groups in P. falciparum and not in T. gondii",
    )

    assert [c.record_class for c in spec.criteria] == ["group"]
    assert spec.record_type == "group"


async def test_a_transform_added_outside_states_the_class_it_returns() -> None:
    held = OperationalSpec(
        goal="groups in P. falciparum and not in T. gondii",
        criteria=[
            Criterion(
                id="step_groups",
                text="groups in P. falciparum and not in T. gondii",
                search_name="GroupsByPhyleticPattern",
                record_class="group",
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_groups")
        ),
    )
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=held,
            answered_spec=held,
            answered_graph=StrategyAst(record_type="group", root=_pattern()),
        ),
    )

    await the_changes_written_outside(
        state, site_id="orthomcl", graph=_graph(_proteins(), "sequence")
    )

    spec = state.domain.operational_spec
    assert spec is not None
    assert {c.id: c.record_class for c in spec.criteria} == {
        "step_groups": "group",
        "step_proteins": "sequence",
    }
    assert spec.record_type == "sequence"


_RETIRED = "GroupsByRetiredSearch"


def _checkpointed() -> OperationalSpec:
    return OperationalSpec(
        goal="groups in P. falciparum and not in T. gondii",
        criteria=[
            Criterion(
                id="step_groups",
                text="groups in P. falciparum and not in T. gondii",
                search_name="GroupsByPhyleticPattern",
            ),
            Criterion(
                id="c_retired",
                text="groups the site no longer lists a search for",
                search_name=_RETIRED,
                open_params=[OpenSlot(param_name="text", param_kind="string")],
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_groups")
        ),
    )


async def test_a_checkpointed_spec_is_classed_by_the_listing_at_turn_entry() -> None:
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=_checkpointed(),
            answered_spec=_checkpointed(),
            answered_graph=StrategyAst(record_type="group", root=_pattern()),
        ),
    )

    await the_changes_written_outside(
        state, site_id="orthomcl", graph=_graph(_pattern(), "group")
    )

    spec = state.domain.operational_spec
    assert spec is not None
    assert {c.id: c.record_class for c in spec.criteria} == {
        "step_groups": "group",
        "c_retired": None,
    }
    ctx = agent_run_context(site_id="orthomcl")
    ctx.deps.agent_state.operational_spec_draft = spec
    asked = FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question="Which text?",
                recommended_value="kinase",
                criterion_id="c_retired",
                param_name="text",
                readings=[Reading(label=v, value=v) for v in ("kinase", "protein")],
            )
        ],
    )
    held = await hold_the_readings_to_the_site(ctx, asked)
    assert isinstance(held, FrameResult)
    assert held.gaps == [
        PassGap(
            kind="record_type_unknown",
            sentence=(
                f"The record type of {_RETIRED} is not known, so the site did not "
                "check the readings of c_retired.text."
            ),
        )
    ]


def _built() -> OperationalSpec:
    return OperationalSpec(
        goal="groups in P. falciparum and not in T. gondii",
        criteria=[
            Criterion(
                id="step_groups",
                text="groups in P. falciparum and not in T. gondii",
                search_name="GroupsByPhyleticPattern",
                record_class="group",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_groups")
        ),
    )


async def test_a_strategy_emptied_outside_drops_the_built_criteria_at_turn_entry() -> (
    None
):
    unbuilt = Criterion(
        id="c_kinases",
        text="kinase groups",
        search_name="GroupsByTextSearch",
        record_class="group",
    )
    plan = _built()
    plan.criteria.append(unbuilt)
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=plan,
            answered_spec=_built(),
            answered_graph=StrategyAst(record_type="group", root=_pattern()),
        ),
    )

    refreshed = await refresh_live_strategy_state(state, lead_runtime("orthomcl"))

    domain = refreshed.domain
    assert domain.operational_spec is not None
    assert domain.answered_spec is not None
    assert (
        [c.id for c in domain.operational_spec.criteria],
        domain.answered_spec.criteria,
        domain.answered_graph,
    ) == (["c_kinases"], [], None)


async def test_a_checkpointed_draft_with_no_strategy_is_classed_at_turn_entry() -> None:
    state = pipeline_state(
        "orthomcl", domain=StrategyDomainState(operational_spec=_checkpointed())
    )

    refreshed = await refresh_live_strategy_state(state, lead_runtime("orthomcl"))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert [c.record_class for c in spec.criteria] == ["group", None]
