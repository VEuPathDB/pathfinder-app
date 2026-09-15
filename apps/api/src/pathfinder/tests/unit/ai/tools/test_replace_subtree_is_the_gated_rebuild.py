"""``replace_subtree`` is the one branch rebuild, and it asks the researcher first.

A batch carries no replacement, so this tool and ``delete_step`` are the two
surfaces that take steps off a strategy.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import JsonValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy_edits import replace_subtree
from pathfinder.ai.tools.toolsets.execution import build_toolset
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    session_with,
)

_STATED = ("step_c1", "step_k3")
_WDK_STEP_IDS = {"step_k1": 101, "step_k2": 102, "step_k3": 103, "step_c1": 301}


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _deps() -> AgentDeps:
    """A spec whose criterion for the kinase branch answers for that whole subtree."""
    root = combine(
        "step_c2",
        combine("step_c1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
        leaf("step_k3"),
    )
    spec = OperationalSpec(
        goal="kinases with mass spec evidence",
        criteria=[
            Criterion(id=step_id, text=step_id, search_name="GenesByTaxon")
            for step_id in _STATED
        ],
    )
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(root, _WDK_STEP_IDS),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=spec),
    )


def test_the_tool_is_approval_gated_like_the_delete() -> None:
    toolset = unwrap_function_toolset(build_toolset())
    gated = {tool.name for tool in toolset.tools.values() if tool.requires_approval}

    assert gated == {"delete_step", "replace_subtree"}


async def test_an_applied_replacement_removes_no_stated_step(
    stub_api: StubAPI,
) -> None:
    """The spec and the graph stay in step: a stated step is refused, not dropped."""
    deps = _deps()
    graph = deps.strategy_session.graph
    assert graph is not None
    before = set(graph.steps)

    payload = returned(
        await replace_subtree(ctx(deps), "step_c1", leaf("step_c1")),
        dict[str, JsonValue],
    )

    stated = {c.id for c in deps.agent_state.operational_spec_draft.criteria}
    removed = before - set(graph.steps)
    assert payload["droppedStepIds"] == sorted(removed)
    assert removed == {"step_k1", "step_k2"}
    assert removed & stated == set()
    assert stated == set(_STATED)
    assert stub_api.named("create_step") != []
