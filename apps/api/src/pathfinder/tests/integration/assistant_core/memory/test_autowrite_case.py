"""A verified turn leaves a case behind, and an unverified one leaves none."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import pytest
from assistant_core.memory.lifespan import lifespan_memory_store
from assistant_core.memory.retrieval import retrieve_relevant_memories
from assistant_core.memory.store import MemoryStore
from assistant_core.platform.db import async_session_factory
from langgraph.runtime import Runtime
from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.build_outcome import BuildOutcome, NodeResult
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.session import StrategySession

from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
    ZeroResultStep,
)
from pathfinder.ai.lead.memory_candidates import PRODUCT_MEMORY_KINDS
from pathfinder.domain.eda_thread import EdaAnalysisFacts, EdaExport
from pathfinder.persistence.models import User
from pathfinder.services.research.literature_search import LiteratureSearchService
from pathfinder.services.research.web_search import WebSearchService


@dataclass
class _Runtime:
    context: Context | None


def _state(
    *,
    user_id: Any,
    success: bool,
    history: list[ZeroResultStep] | None = None,
) -> PipelineState:
    spec = OperationalSpec(
        goal="kinases",
        interpreted_goal="Plasmodium falciparum kinases",
        criteria=[
            Criterion(
                id="s1",
                text="kinase domain",
                search_name="GenesByGoTerm",
                role="seed",
                resolved_params={"go_term": StringValue(value="GO:0004672")},
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="s1")),
    )
    outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=330423363,
        counts={"s1": 142},
        root_count=142,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesByGoTerm",
                count=142,
                status="ok",
            ),
        ],
    )
    return PipelineState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find the kinases",
        domain=StrategyDomainState(
            operational_spec=spec,
            original_request="find every kinase in P. falciparum",
            last_build_outcome=outcome,
            zero_result_history=list(history or []),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="142 kinases",
                reason="verified",
                success=success,
            ),
        ),
    )


def _eda_state(*, user_id: Any) -> PipelineState:
    """A verified EDA turn: an exported step, and no framed criteria at all."""
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="export the genes up in the heat-shocked samples",
        domain=StrategyDomainState(
            original_request="which genes go up under heat shock in P. berghei",
            eda_analysis=EdaAnalysisFacts(
                site_id="plasmodb",
                dataset_id="DS_53f554ec6a",
                study_id="DS_53f554ec6a",
                analysis_id="t4fszEJ",
                study_display_name="Heat shock RNA-Seq (Su et al.)",
                display_name="febrile versus normal",
                num_filters=1,
                num_computations=1,
                filter_summaries=["Species is P. berghei"],
                can_export_rows=True,
            ),
            last_build_outcome=BuildOutcome(
                pushed_step_ids=["step_1"],
                wdk_strategy_id=330423363,
                counts={"step_1": 1543},
                root_count=1543,
                node_results=[
                    NodeResult(
                        node_id="step_1",
                        search_name="GenesByEdaVizWithCompute",
                        count=1543,
                        status="ok",
                    ),
                ],
            ),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="1543 genes",
                reason="verified",
                success=True,
            ),
        ),
    )
    state.turn_markers.eda_export = EdaExport(
        search_name="GenesByEdaVizWithCompute",
        step_id="step_1",
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        is_compute_backed=True,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upAndDown",
    )
    return state


async def _seed_user() -> Any:
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


def _context(user_id: Any, store: Any) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=async_session_factory,
        web_search_service=WebSearchService(),
        literature_search_service=LiteratureSearchService(),
        cancel_event=asyncio.Event(),
        memory_store=store,
    )


@pytest.fixture
def no_compaction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _skip(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(nodes, "maybe_compact_scratchpad", _skip)


@pytest.mark.asyncio
async def test_a_verified_turn_writes_a_case(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        state = _state(user_id=user_id, success=True)
        await nodes.finalize_turn_node(
            state,
            cast("Runtime[Context]", _Runtime(context=_context(user_id, raw))),
        )
        cases = await MemoryStore(store=raw).list_all(user_id=user_id, kind="case")

    assert len(cases) == 1
    assert cases[0].value.content["root_count"] == 142
    assert cases[0].value.content["goal"] == "find every kinase in P. falciparum"


@pytest.mark.asyncio
async def test_a_failed_digest_writes_no_case(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        state = _state(user_id=user_id, success=False)
        await nodes.finalize_turn_node(
            state,
            cast("Runtime[Context]", _Runtime(context=_context(user_id, raw))),
        )
        cases = await MemoryStore(store=raw).list_all(user_id=user_id, kind="case")

    assert cases == []


@pytest.mark.asyncio
async def test_the_same_case_twice_leaves_one_row(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        runtime = cast("Runtime[Context]", _Runtime(context=_context(user_id, raw)))
        for _ in range(2):
            await nodes.finalize_turn_node(
                _state(user_id=user_id, success=True), runtime
            )
        cases = await MemoryStore(store=raw).list_all(user_id=user_id, kind="case")

    assert len(cases) == 1


@pytest.mark.asyncio
async def test_a_recovery_case_names_what_emptied_and_what_fixed_it(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    history = [
        ZeroResultStep(search_name="GenesByGoTerm", criterion_text="kinase domain"),
    ]
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        state = _state(user_id=user_id, success=True, history=history)
        await nodes.finalize_turn_node(
            state,
            cast("Runtime[Context]", _Runtime(context=_context(user_id, raw))),
        )
        cases = await MemoryStore(store=raw).list_all(user_id=user_id, kind="case")

    recoveries = [c for c in cases if c.value.content["case"] == "recovery"]
    assert len(recoveries) == 1
    assert recoveries[0].value.content["emptied_search"] == "GenesByGoTerm"
    assert recoveries[0].value.content["fixed_params"] == {"go_term": "GO:0004672"}


@pytest.mark.asyncio
async def test_a_later_turn_retrieves_the_case_for_a_similar_goal(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    """The case reaches the next run through the same retrieval the Lead uses."""
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        await nodes.finalize_turn_node(
            _state(user_id=user_id, success=True),
            cast("Runtime[Context]", _Runtime(context=_context(user_id, raw))),
        )
        found = await retrieve_relevant_memories(
            store=MemoryStore(store=raw),
            user_id=user_id,
            query="which kinases does P. falciparum have",
            site_id="plasmodb",
            kinds=PRODUCT_MEMORY_KINDS,
        )

    assert "case" in [stored.value.kind for stored in found]


@pytest.mark.asyncio
async def test_a_verified_eda_export_writes_a_case(
    db_cleaner: None,
    patch_app_db_engine: None,
    no_compaction: None,
) -> None:
    """The EDA arc frames no criteria, and its verified turn still leaves a case."""
    del db_cleaner, patch_app_db_engine, no_compaction
    user_id = await _seed_user()
    async with lifespan_memory_store(os.environ["DATABASE_URL"]) as raw:
        await nodes.finalize_turn_node(
            _eda_state(user_id=user_id),
            cast("Runtime[Context]", _Runtime(context=_context(user_id, raw))),
        )
        cases = await MemoryStore(store=raw).list_all(user_id=user_id, kind="case")

    assert len(cases) == 1
    content = cases[0].value.content
    assert content["case"] == "eda-export"
    assert content["exported_count"] == 1543
    assert content["study"] == "Heat shock RNA-Seq (Su et al.)"
    assert content["search_name"] == "GenesByEdaVizWithCompute"
    assert content["goal"] == "which genes go up under heat shock in P. berghei"
