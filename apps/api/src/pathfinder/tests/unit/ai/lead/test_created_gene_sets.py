"""Every gene set a turn creates reaches the turn's memory candidates."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.memory.embedding import format_embedded_string
from assistant_core.memory.schemas import MemoryValue
from langgraph.runtime import Runtime
from langgraph.store.postgres.aio import AsyncPostgresStore
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_delta import _build_state_delta
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead import lead_tools
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import workbench
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

GENE_IDS = ["PF3D7_0709000", "PF3D7_1133400"]
SET_NAME = "gametocyte candidates"


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[GeneSet]:
    kept: list[GeneSet] = []
    monkeypatch.setattr(workbench, "save_gene_set", kept.append)
    return kept


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="save these 2 genes as a gene set"))


def _domain_after_the_turn(deps: LeadDeps) -> StrategyDomainState:
    """The domain the Lead's node writes back when the turn ends."""
    domain = _build_state_delta(
        state=deps.state, deps=deps, capture=_LeadRunCapture(), memories=[]
    )["domain"]
    assert isinstance(domain, StrategyDomainState)
    return domain


def _verification_save() -> Any:
    """The save as verification registers it, through its own toolset."""
    toolset = verification.build_toolset()
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    assert isinstance(toolset, FunctionToolset)
    return toolset.tools["create_workbench_gene_set"].function


async def test_a_save_through_the_leads_wrapper_records_the_set(
    saved: list[GeneSet],
) -> None:
    deps = _deps()

    await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
    )

    recorded = _domain_after_the_turn(deps).created_gene_sets
    assert [(c.id, c.name, c.gene_count) for c in recorded] == [
        (saved[0].id, SET_NAME, len(GENE_IDS))
    ]


async def test_a_save_through_verifications_toolset_records_the_set(
    saved: list[GeneSet],
) -> None:
    """The sub-agent runs under its own deps, and the turn still records it."""
    deps = _deps()
    inner: AgentDeps = agent_deps_for(deps)

    await _verification_save()(
        run_context_for(inner, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
    )

    recorded = _domain_after_the_turn(deps).created_gene_sets
    assert [(c.id, c.name, c.gene_count) for c in recorded] == [
        (saved[0].id, SET_NAME, len(GENE_IDS))
    ]


async def _one_note(deps: LeadDeps) -> MemoryValue:
    await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
    )
    deps.state.domain = _domain_after_the_turn(deps)
    notes = [
        value
        for value, _key in collect_memory_candidates(deps.state)
        if value.kind == "gene_set_note"
    ]
    assert len(notes) == 1
    return notes[0]


async def test_a_recorded_set_becomes_one_gene_set_note(
    saved: list[GeneSet],
) -> None:
    deps = _deps()

    await _one_note(deps)
    keys = [
        key
        for value, key in collect_memory_candidates(deps.state)
        if value.kind == "gene_set_note"
    ]

    assert keys == [f"gene_set_note:{saved[0].id}"]


async def test_the_note_embeds_what_the_researcher_called_the_set(
    saved: list[GeneSet],
) -> None:
    """The store embeds kind, name, tags and summary, and retrieval reads that."""
    del saved
    deps = _deps()

    embedded = format_embedded_string(await _one_note(deps))

    assert SET_NAME in embedded
    assert "2 genes" in embedded


class _StoreStub(AsyncPostgresStore):
    """A store the node can hold while the auto-write itself is stood in for."""

    def __init__(self) -> None:
        self._task = None


class _NoTombstones:
    def __init__(self, *, session_factory: Any) -> None:
        del session_factory

    async def existing_hashes(
        self, *, user_id: UUID, values: Any
    ) -> set[tuple[str, str]]:
        del user_id, values
        return set()


async def test_a_written_note_leaves_the_created_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A note in the store is not offered again, so the write stays bounded."""

    async def _nothing(**kwargs: Any) -> None:
        del kwargs

    async def _no_candidates(_state: PipelineState) -> list[Any]:
        return []

    async def _wrote(**kwargs: Any) -> int:
        del kwargs
        return 1

    monkeypatch.setattr(nodes, "write_turn_message", _nothing)
    monkeypatch.setattr(nodes, "collect_turn_memory_candidates", _no_candidates)
    monkeypatch.setattr(nodes, "auto_write_memories", _wrote)
    monkeypatch.setattr(nodes, "TombstoneRepository", _NoTombstones)
    monkeypatch.setattr(nodes, "compact_scratchpad", _nothing)
    deps = _deps()
    await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"), name=SET_NAME, gene_ids=GENE_IDS
    )
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=SET_NAME,
        domain=_domain_after_the_turn(deps).model_copy(
            update={
                "verification_digest": VerificationDigest(
                    disposition=PhaseDisposition.DONE,
                    prose="ok",
                    reason="verified",
                    success=True,
                )
            }
        ),
    )
    runtime: Runtime[Context] = Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
            memory_store=_StoreStub(),
        )
    )

    assert state.domain.created_gene_sets
    command = await nodes.finalize_turn_node(state, runtime)

    update = command.update
    assert isinstance(update, dict)
    domain = update["domain"]
    assert isinstance(domain, StrategyDomainState)
    assert domain.created_gene_sets == []
