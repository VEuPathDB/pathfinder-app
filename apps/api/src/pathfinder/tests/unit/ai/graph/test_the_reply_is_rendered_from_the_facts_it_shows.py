"""The reply's text part is its prose with each reference rendered from the
same facts the facts part beside it shows, and a card's reply the same way."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from langgraph.runtime import Runtime
from pydantic_ai.ui.vercel_ai.response_types import (
    TextDeltaChunk,
    ToolInputAvailableChunk,
    ToolInputStartChunk,
    ToolOutputDeniedChunk,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import lead_node
from pathfinder.ai.graph._lead_capture import _emit_residual_prose, _LeadRunCapture
from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.graph._lead_emit import release_the_cards
from pathfinder.ai.graph._lead_facts import show_the_facts
from pathfinder.ai.graph._lead_stops import loop_stop_prose, stop_response
from pathfinder.ai.graph.lead_node import _run_lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import SourceFact, StepFact, TurnFacts
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.database import no_database
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# microsporidiadb, build 71: E. intestinalis signal peptide 66, the E. cuniculi
# ortholog exclusion 129, 9 in both.
_PROSE = (
    "The signal peptide step returns [count:step_sp] and the result [root], so "
    "the ortholog filter removes [diff:step_sp,root]."
)


def _session() -> StrategySession:
    root = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_sp", search_name="GenesWithSignalPeptide"
        ),
        secondary_input=StrategyStepNode(
            id="step_orth", search_name="GenesByOrthologPattern"
        ),
    )
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id="microsporidiadb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id="microsporidiadb")
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={"step_sp": 66, "step_orth": 129, "step_join": 9}
    )
    return session


async def _turn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    payloads: list[object] = []

    async def _answered(
        *, deps: LeadDeps, capture: _LeadRunCapture, **_kwargs: Any
    ) -> None:
        del deps
        capture.response = LeadResponse(prose=_PROSE, strategy_changed=False)

    async def _pre_turn(state: PipelineState, _context: Context) -> PipelineState:
        return state

    async def _nothing(*_args: Any) -> list[object]:
        return []

    monkeypatch.setattr(lead_node, "get_stream_writer", lambda: payloads.append)
    monkeypatch.setattr(lead_node, "retrieve_memories", _nothing)
    monkeypatch.setattr(lead_node, "_drive_lead_stream", _answered)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="microsporidiadb",
        mode="strategy",
        user_prompt="how many genes would there be without the ortholog filter",
    )
    runtime = Runtime(
        context=Context(
            site_id="microsporidiadb",
            user_id=uuid4(),
            strategy_session=_session(),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )
    await _run_lead_turn(
        state, runtime, pre_turn=_pre_turn, build_agent=build_lead_agent
    )
    return [chunk for p in payloads if (chunk := _extract_chunk(p)) is not None]


async def test_the_text_part_is_the_prose_rendered_from_the_facts_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = await _turn(monkeypatch)
    (shown,) = [chunk["data"] for chunk in written if chunk["type"] == "data-facts"]
    text = [chunk["delta"] for chunk in written if chunk["type"] == "text-delta"]

    assert text == [
        (
            "The signal peptide step returns 66 genes and the result 9 genes, so "
            "the ortholog filter removes 57 genes."
        )
    ]
    assert text == [render_reply(_PROSE, TurnFacts.model_validate(shown))]


def test_a_cards_reply_is_rendered_from_the_facts_it_is_released_with() -> None:
    hold = CardHold()
    reply = "The step returns [count:c_text]. Which field should it search?"
    hold.admit(ToolInputStartChunk(tool_call_id="call_card", tool_name="consult_user"))
    hold.admit(
        ToolInputAvailableChunk(
            tool_call_id="call_card",
            tool_name="consult_user",
            input={"questions": [], "reply": reply},
        )
    )
    facts = TurnFacts(steps=[StepFact(step_id="c_text", display_name="Text", count=2)])

    released = hold.release(facts)

    assert [c.delta for c in released if isinstance(c, TextDeltaChunk)] == [
        "The step returns 2 genes. Which field should it search?"
    ]


def _card(call_id: str, reply: str) -> list[Any]:
    return [
        ToolInputStartChunk(tool_call_id=call_id, tool_name="consult_user"),
        ToolInputAvailableChunk(
            tool_call_id=call_id,
            tool_name="consult_user",
            input={"questions": [], "reply": reply},
        ),
    ]


def test_a_card_turn_shows_the_facts_once_and_renders_only_the_shown_card() -> None:
    payloads: list[object] = []
    deps = lead_deps(pipeline_state("microsporidiadb"), strategy_session=_session())
    capture = _LeadRunCapture()
    hold = CardHold()
    for chunk in (
        *_card("call_refused", "It returns 66 genes. Which field?"),
        ToolOutputDeniedChunk(tool_call_id="call_refused"),
        *_card("call_shown", "It returns [count:step_sp]. Which field?"),
    ):
        hold.admit(chunk)

    release_the_cards(payloads.append, hold, deps, capture, {})
    facts = show_the_facts(payloads.append, deps, capture)
    _emit_residual_prose(payloads.append, capture, message_id=uuid4())
    written = [c for p in payloads if (c := _extract_chunk(p)) is not None]

    assert [c["type"] for c in written] == [
        "data-facts",
        "text-start",
        "text-delta",
        "text-end",
        "tool-input-start",
        "tool-input-available",
    ]
    assert [c["delta"] for c in written if c["type"] == "text-delta"] == [
        render_reply("It returns [count:step_sp]. Which field?", facts)
    ]
    assert facts is capture.facts


def test_the_records_a_facts_part_lists_are_kept_with_their_pages() -> None:
    session = _session()
    session.sync_state = WDKSyncState(
        step_counts={"step_sp": 66, "step_orth": 129, "step_join": 9},
        wdk_step_ids={"step_sp": 101, "step_orth": 102, "step_join": 103},
    )
    deps = lead_deps(pipeline_state("microsporidiadb"), strategy_session=session)
    deps.state.turn_markers.record_listed_genes(103, ["Eint_010010", "Eint_020050"])

    show_the_facts([].append, deps, _LeadRunCapture())

    assert deps.state.domain.shown_records == [
        SourceFact(url=gene_record_url("microsporidiadb", g), record_id=g)
        for g in ("Eint_010010", "Eint_020050")
    ]


def test_a_stop_reply_the_runtime_writes_passes_through_the_renderer_unchanged() -> (
    None
):
    payloads: list[object] = []
    capture = _LeadRunCapture()
    capture.response = stop_response(loop_stop_prose(None), changed=False)

    _emit_residual_prose(payloads.append, capture, message_id=uuid4())

    assert [
        c["delta"]
        for p in payloads
        if (c := _extract_chunk(p)) is not None and c["type"] == "text-delta"
    ] == [loop_stop_prose(None)]
