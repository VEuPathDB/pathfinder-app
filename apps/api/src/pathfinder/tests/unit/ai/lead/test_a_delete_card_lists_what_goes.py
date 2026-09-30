"""A delete card lists every step the delete removes, computed before the card
(the root union of a 383-gene and a 440-gene search takes both), in full beside
its one-line question, and the approved delete removes exactly those steps."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.ai.lead import deleted_steps
from pathfinder.ai.lead._delete_rules import delete_cascade
from pathfinder.ai.lead.deleted_steps import ask_about_the_removals
from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.live_state import LiveStepState, LiveStrategyState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_runtime,
    pipeline_state,
)
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    session_with,
)

_UNION = "step_e617d25c"
_GS = "step_85ff1742"
_WB = "c_ankyrin_wb"
_LIVE = LiveStrategyState(
    wdk_strategy_id=330855793,
    step_count=3,
    root_count=823,
    steps=[
        LiveStepState(step_id=_UNION, display_name="Union", estimated_size=823),
        LiveStepState(
            step_id=_GS,
            display_name="InterPro Domain",
            search_name="GenesByInterproDomain",
            estimated_size=383,
        ),
        LiveStepState(
            step_id=_WB,
            display_name="InterPro Domain",
            search_name="GenesByInterproDomain",
            estimated_size=440,
        ),
    ],
)


def _union() -> StrategyStepNode:
    return combine(
        _UNION,
        StrategyStepNode(
            id=_GS, search_name="GenesByInterproDomain", display_name="InterPro Domain"
        ),
        StrategyStepNode(
            id=_WB, search_name="GenesByInterproDomain", display_name="InterPro Domain"
        ),
        CombineOp.UNION,
    )


def test_the_cascade_of_the_root_union_holds_its_secondary_branch() -> None:
    session = session_with(_union(), {})
    assert session.graph is not None

    assert delete_cascade(session.graph, session.sync_state, _UNION) == [_WB, _UNION]
    assert sorted(session.graph.steps) == sorted([_UNION, _GS, _WB])


async def test_the_card_lists_every_step_the_delete_removes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _live(*_args: object) -> LiveStrategyState:
        return _LIVE

    monkeypatch.setattr(deleted_steps, "read_live_state", _live)
    deps = LeadDeps(
        state=pipeline_state(user_prompt="Which isolate has more? Drop the union."),
        intent=None,
        runtime=lead_runtime(strategy_session=session_with(_union(), {})),
        retrieved_memories=[],
    )
    writer = ChunkCollector()

    await ask_about_the_removals(
        deps,
        DeferredToolRequests(
            approvals=[ToolCallPart("delete_step", {"step_id": _UNION}, "call_delete")]
        ),
        writer,
    )

    assert deps.state.turn_markers.delete_cards == {"call_delete": [_WB, _UNION]}
    assert [s["summary"] for s in writer.data_of("data-tool-summary")] == [
        "Delete step 'Union' (823 genes)?"
    ]
    assert writer.data_of("data-delete-cascade") == [
        {
            "toolCallId": "call_delete",
            "removes": ["'InterPro Domain' (GenesByInterproDomain, 440 genes)"],
        }
    ]


def _chain(depth: int) -> tuple[StrategyStepNode, LiveStrategyState]:
    """A root with ``depth`` nested intersects, each over a long-named search."""
    title = "Transmembrane Domain Count"
    search = "GenesByTransmembraneDomains"
    node = StrategyStepNode(id="leaf_0", search_name=search, display_name=title)
    steps = [
        LiveStepState(
            step_id="leaf_0", display_name=title, search_name=search, estimated_size=840
        )
    ]
    for level in range(1, depth + 1):
        leaf = StrategyStepNode(
            id=f"leaf_{level}", search_name=search, display_name=title
        )
        node = combine(f"and_{level}", leaf, node, CombineOp.INTERSECT)
        steps += [
            LiveStepState(
                step_id=f"leaf_{level}",
                display_name=title,
                search_name=search,
                estimated_size=1_871,
            ),
            LiveStepState(
                step_id=f"and_{level}", display_name="Intersect", estimated_size=116
            ),
        ]
    live = LiveStrategyState(
        wdk_strategy_id=1, step_count=len(steps), root_count=116, steps=steps
    )
    return node, live


async def test_a_cascade_past_one_line_names_each_step_in_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, live = _chain(3)

    async def _live(*_args: object) -> LiveStrategyState:
        return live

    monkeypatch.setattr(deleted_steps, "read_live_state", _live)
    deps = LeadDeps(
        state=pipeline_state(user_prompt="Drop the top intersect."),
        intent=None,
        runtime=lead_runtime(strategy_session=session_with(root, {})),
        retrieved_memories=[],
    )
    writer = ChunkCollector()

    await ask_about_the_removals(
        deps,
        DeferredToolRequests(
            approvals=[ToolCallPart("delete_step", {"step_id": "and_3"}, "call_top")]
        ),
        writer,
    )

    removed = deps.state.turn_markers.delete_cards["call_top"]
    (cascade,) = writer.data_of("data-delete-cascade")
    assert len(cascade["removes"]) == len(removed) - 1 > 1
    assert (
        "'Transmembrane Domain Count' (GenesByTransmembraneDomains, 1,871 genes)"
        in (cascade["removes"])
    )
    assert [s["summary"] for s in writer.data_of("data-tool-summary")] == [
        "Delete step 'Intersect' (116 genes)?"
    ]


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


@pytest.mark.usefixtures("stub_api")
async def test_the_approved_delete_removes_exactly_the_steps_the_card_listed() -> None:
    session = session_with(_union(), {})
    assert session.graph is not None
    listed = delete_cascade(session.graph, session.sync_state, _UNION)
    ctx = lead_run_context(
        user_prompt="Drop the union.",
        strategy_session=session,
        tool_call_id="call_delete",
    )

    answer = await delete_step(
        ctx, step_id=_UNION, reply="The union goes, and its WB branch goes with it."
    )

    assert returned(answer, dict[str, JsonValue])["deleted"] == listed
    assert sorted(session.graph.steps) == [_GS]


@pytest.mark.usefixtures("stub_api")
async def test_a_delete_whose_steps_changed_since_the_card_is_refused() -> None:
    session = session_with(_union(), {})
    ctx = lead_run_context(
        user_prompt="Drop the union.",
        strategy_session=session,
        tool_call_id="call_delete",
    )
    ctx.deps.state.turn_markers.delete_cards["call_delete"] = [_GS, _UNION]

    with pytest.raises(ToolFailed) as refused:
        await delete_step(
            ctx, step_id=_UNION, reply="The union goes, and its WB branch goes with it."
        )

    assert str(refused.value) == (
        f"The strategy changed while the card waited: deleting {_UNION} now removes "
        f"{_WB}, {_UNION}, and the card listed {_GS}, {_UNION}. Nothing was removed. "
        "Call delete_step again so its card lists what goes now."
    )
    assert session.graph is not None
    assert sorted(session.graph.steps) == sorted([_UNION, _GS, _WB])
