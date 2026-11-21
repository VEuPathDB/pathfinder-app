from __future__ import annotations

import asyncio
from uuid import uuid4

from assistant_core.conversation.serde import build_checkpoint_serde
from veupathdb.domain.parameters import StringValue

from strategist.ai.graph.runtime import Context
from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.ai.lead.dispatch_context import the_edit_the_strategy_owes
from strategist.ai.lead.pre_turn import refresh_live_strategy_state
from strategist.assistants.strategist_spec import STRATEGIST_CHECKPOINT_TYPES
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.session import StrategySession
from strategist.domain.strategy.site_set_reads import SiteSetReads
from strategist.tests._support.database import no_database


def _text(**values: str) -> OperationalSpec:
    return OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="c_text",
                text="kinases",
                search_name="GenesByText",
                resolved_params={
                    name: BoundValue(value=StringValue(value=value), source="stated")
                    for name, value in values.items()
                },
            )
        ],
    )


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _state(domain: StrategyDomainState) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=domain,
    )


async def test_the_turn_follows_the_catalog_over_the_names_it_carried() -> None:
    held = _text(text_expression="kinase")
    state = _state(
        StrategyDomainState(
            operational_spec=held,
            answered_spec=held,
            site_set=SiteSetReads(
                by_search={"GenesByText": frozenset({"text_fields"})}
            ),
        )
    )

    refreshed = await refresh_live_strategy_state(state, _context())
    _, owed = the_edit_the_strategy_owes(
        refreshed, _text(text_expression="kinase", document_type="gene")
    )

    assert refreshed.domain.site_set == SiteSetReads(
        by_search={"GenesByText": frozenset({"document_type"})}
    )
    assert [c.disposition for c in owed.changes] == ["kept"]


def test_a_domain_with_names_writes_no_site_set_to_the_checkpoint() -> None:
    serde = build_checkpoint_serde(STRATEGIST_CHECKPOINT_TYPES)
    named = StrategyDomainState(
        site_set=SiteSetReads(by_search={"GenesByText": frozenset({"document_type"})})
    )

    assert serde.dumps_typed(named) == serde.dumps_typed(StrategyDomainState())
