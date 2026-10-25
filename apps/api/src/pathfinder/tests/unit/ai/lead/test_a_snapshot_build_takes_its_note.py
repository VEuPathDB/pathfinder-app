"""A build of a spec bound to a saved computed comparison writes the snapshot
note the site shows as the strategy's description."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.parameters import InputDatasetValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.computed_groups import SNAPSHOT_NOTE
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.tests._support.computed_comparison import held_comparison
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.domain.strategy.test_a_comparison_names_its_breakdown import (
    _PATTERN,
)

_DATASET = "202394260"


def _ctx(saved: str) -> RunContext[LeadDeps]:
    held = held_comparison(_PATTERN, date(2026, 10, 25)).model_copy(
        update={"dataset_id": saved}
    )
    spec = OperationalSpec(
        goal="groups with more proteins per genome in the left set",
        criteria=[
            Criterion(
                id="c_groups",
                text="groups with more proteins per genome in the left set",
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
    state = pipeline_state(
        "orthomcl",
        user_prompt="groups with more proteins per genome in the left set",
        domain=StrategyDomainState(
            operational_spec=spec, computed_comparisons={held.handle: held}
        ),
    )
    return run_context_for(
        lead_deps(state, strategy_session=StrategySession(site_id="orthomcl"))
    )


async def _noted(monkeypatch: pytest.MonkeyPatch, saved: str) -> str | None:
    contexts: list[StrategyMutationContext] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        contexts.append(kwargs["deps"])
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    await build_strategy(_ctx(saved))
    [context] = contexts
    return context.wdk_description


async def test_a_build_of_a_saved_comparison_writes_the_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _noted(monkeypatch, _DATASET) == SNAPSHOT_NOTE


async def test_a_build_of_another_list_writes_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert [await _noted(monkeypatch, "1")] == [None]
