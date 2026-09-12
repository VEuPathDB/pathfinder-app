"""What a turn offers the memory store, per kind."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.memory.schemas import MemoryEntryDraft, MemoryValue

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_PREFERENCE = (
    "Please remember for future sessions: I always work with P. falciparum 3D7."
)


def _intent_state(classification: IntentClassification | None) -> PipelineState:
    intent = (
        None
        if classification is None
        else UserIntent(
            classification=classification,
            inferred_goal="store a default organism",
        )
    )
    return pipeline_state(
        user_prompt=_PREFERENCE,
        domain=StrategyDomainState(
            user_intent=intent,
            operational_spec=OperationalSpec(
                goal=_PREFERENCE,
                interpreted_goal=_PREFERENCE,
                criteria=[
                    Criterion(id="c1", text="organism", search_name="GenesByTaxon"),
                ],
            ),
        ),
    )


def _strategy_keys(state: PipelineState) -> list[str]:
    return [
        key
        for value, key in collect_memory_candidates(state)
        if value.kind == "strategy"
    ]


@pytest.mark.parametrize(
    "classification",
    [
        IntentClassification.MEMORY_REQUEST,
        IntentClassification.CONTEXT_STATEMENT,
        IntentClassification.FOLLOW_UP_QUESTION,
        IntentClassification.OFF_TOPIC,
        IntentClassification.DENIAL,
    ],
)
def test_a_turn_that_was_not_asked_to_build_writes_no_strategy_memory(
    classification: IntentClassification,
) -> None:
    assert _strategy_keys(_intent_state(classification)) == []


def test_a_build_turn_still_writes_its_strategy_memory() -> None:
    state = _intent_state(IntentClassification.NEW_STRATEGY)

    assert _strategy_keys(state) == [f"strategy:{state.conversation_id.hex}"]


def test_an_unclassified_turn_still_writes_its_strategy_memory() -> None:
    state = _intent_state(None)

    assert _strategy_keys(state) == [f"strategy:{state.conversation_id.hex}"]


def _digest_state(*, digest: VerificationDigest | None) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find Plasmodium kinases",
        domain=StrategyDomainState(verification_digest=digest),
    )


def _digest(remember: list[MemoryEntryDraft]) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Strategy returned 142 Plasmodium kinases. Sample records "
        "look correct, GO enrichment confirms kinase activity.",
        reason="verification passed",
        success=True,
        key_findings=["142 hits", "GO:0016301 enrichment p<1e-12"],
        caveats=[],
        remember=remember,
    )


def _knowledge(state: PipelineState) -> list[MemoryValue]:
    return [
        value
        for value, _key in collect_memory_candidates(state)
        if value.kind == "knowledge"
    ]


def test_no_remember_yields_no_knowledge_candidates() -> None:
    assert _knowledge(_digest_state(digest=_digest(remember=[]))) == []


def test_no_digest_yields_no_knowledge_candidates() -> None:
    assert _knowledge(_digest_state(digest=None)) == []


def test_remember_lifts_to_full_memory_value() -> None:
    """The site and the source conversation come from state, not the model."""
    draft = MemoryEntryDraft(
        name="P. falciparum kinome size",
        summary="P. falciparum 3D7 has ~142 protein kinases by GO:0016301",
        content={
            "organism": "P. falciparum 3D7",
            "go_term": "GO:0016301",
            "count": 142,
            "method": "GenesByGoTerm + transmembrane filter",
        },
        tags=["kinome", "kinase"],
    )
    state = _digest_state(digest=_digest(remember=[draft]))

    knowledge = _knowledge(state)

    assert len(knowledge) == 1
    value = knowledge[0]
    assert value.name == "P. falciparum kinome size"
    assert value.summary.startswith("P. falciparum 3D7 has ~142")
    assert value.content["count"] == 142
    assert value.content["go_term"] == "GO:0016301"
    assert value.site_id == "plasmodb"
    assert value.source_conversation_id == state.conversation_id
    assert value.tags == ["kinome", "kinase", "plasmodb"]


def test_existing_site_tag_not_duplicated() -> None:
    draft = MemoryEntryDraft(
        name="x", summary="y", content={"k": "v"}, tags=["plasmodb", "extra"]
    )

    value = _knowledge(_digest_state(digest=_digest(remember=[draft])))[0]

    assert value.tags == ["plasmodb", "extra"]


def test_multiple_drafts_get_distinct_keys() -> None:
    """Each draft gets its own key, so a repeated write updates its memory."""
    drafts = [
        MemoryEntryDraft(name=f"finding {i}", summary=f"summary {i}", content={"i": i})
        for i in range(3)
    ]
    state = _digest_state(digest=_digest(remember=drafts))

    keys = [
        key
        for value, key in collect_memory_candidates(state)
        if value.kind == "knowledge"
    ]

    assert keys == [f"knowledge:{state.conversation_id.hex}:{idx}" for idx in range(3)]
