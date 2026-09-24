"""The evidence card of one check, read from the records the turn already holds.

The assembler takes no model output: the control tests the turn recorded, the
build's step counts, one read of the strategy on the site, and the references
each criterion was bound on.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from veupathdb.wdk import get_site

from pathfinder.ai.graph.stream_events import evidence_card_event
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets._dynamic import live_wdk_step_ids
from pathfinder.domain.evidence import (
    CheckedStepCount,
    ControlEnrichment,
    ControlTestEvidence,
    CriterionCitations,
    EvidenceCard,
    EvidenceVerdict,
    SiteRead,
)
from pathfinder.domain.strategy.build_outcome import NodeResult
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.services.enrichment.stats import hypergeometric_log_sf
from pathfinder.services.strategies.site_counts import SiteCounts, read_step_counts


@dataclass(frozen=True)
class CardSources:
    """Every record one card is read from, apart from the site's answer."""

    check_id: str
    revision: str
    site_id: str
    # The label each step of the judged strategy carries, by step id.
    labels: Mapping[str, str]
    live_wdk_step_ids: frozenset[int]
    wdk_strategy_id: int | None
    # The root the strategy was pushed with, for a site that does not answer.
    root_wdk_step_id: int | None
    node_results: Sequence[NodeResult]
    spec: OperationalSpec | None
    control_tests: Sequence[ControlTestRun]
    verdict: EvidenceVerdict


def _strategy_url(sources: CardSources, site: SiteCounts | None) -> str | None:
    """The step page of the strategy on the site, where its analyses run."""
    if sources.wdk_strategy_id is None:
        return None
    root = sources.root_wdk_step_id if site is None else site.root_step_id
    return get_site(sources.site_id).strategy_url(sources.wdk_strategy_id, root)


def _steps(sources: CardSources, site: SiteCounts | None) -> list[CheckedStepCount]:
    return [
        CheckedStepCount(
            step_id=result.node_id,
            wdk_step_id=result.wdk_step_id,
            title=sources.labels.get(result.node_id, result.search_name),
            recorded_count=result.count,
            site_count=None if site is None else site.counts.get(result.wdk_step_id),
        )
        for result in sources.node_results
        if result.wdk_step_id is not None
        and result.wdk_step_id in sources.live_wdk_step_ids
    ]


def _with_enrichment(tested: ControlTestEvidence) -> ControlTestEvidence:
    """The test with the hypergeometric row, when it ran both kinds."""
    positive, negative = tested.positive, tested.negative
    if positive is None or negative is None:
        return tested
    population = positive.controls_count + negative.controls_count
    returned = positive.returned_count + negative.returned_count
    log_sf = hypergeometric_log_sf(
        positive.returned_count, population, positive.controls_count, returned
    )
    return tested.model_copy(
        update={
            "enrichment": ControlEnrichment(
                population=population,
                positives=positive.controls_count,
                returned=returned,
                positives_returned=positive.returned_count,
                p_value=min(1.0, math.exp(log_sf)),
            )
        }
    )


def _controls(sources: CardSources) -> list[ControlTestEvidence]:
    """The latest control test of each target the judged strategy still holds."""
    latest: dict[tuple[int | None, str], ControlTestEvidence] = {}
    for run in sources.control_tests:
        if run.origin != "control_test":
            continue
        tested = run.evidence
        step = tested.wdk_step_id
        if step is not None and step not in sources.live_wdk_step_ids:
            continue
        latest[step, tested.tested_label] = tested
    return [_with_enrichment(tested) for tested in latest.values()]


def _citations(spec: OperationalSpec | None) -> list[CriterionCitations]:
    if spec is None:
        return []
    return [
        CriterionCitations(
            criterion_id=criterion.id,
            criterion_text=criterion.text,
            references=list(criterion.rationale.sources),
        )
        for criterion in spec.criteria
        if criterion.rationale is not None and criterion.rationale.sources
    ]


def _site_read(sources: CardSources, site: SiteCounts | None) -> SiteRead:
    if sources.wdk_strategy_id is None:
        return "not_read"
    return "not_answered" if site is None else "read"


def assemble_evidence_card(
    sources: CardSources, site: SiteCounts | None, *, checked_at: datetime
) -> EvidenceCard:
    """The card, every value read from ``sources`` or from the site's answer."""
    return EvidenceCard(
        check_id=sources.check_id,
        revision=sources.revision,
        site_id=sources.site_id,
        checked_at=checked_at,
        wdk_strategy_id=sources.wdk_strategy_id,
        strategy_url=_strategy_url(sources, site),
        site_read=_site_read(sources, site),
        steps=_steps(sources, site),
        controls=_controls(sources),
        citations=_citations(sources.spec),
        verdict=sources.verdict,
    )


def _sources(
    deps: LeadDeps, *, check_id: str, revision: str, verdict: EvidenceVerdict
) -> CardSources:
    session = deps.runtime.strategy_session
    graph = session.get_graph(None)
    sync = session.sync_state
    return CardSources(
        check_id=check_id,
        revision=revision,
        site_id=deps.runtime.site_id,
        labels={}
        if graph is None
        else {step_id: step.display_label for step_id, step in graph.steps.items()},
        live_wdk_step_ids=frozenset(live_wdk_step_ids(session)),
        wdk_strategy_id=None if sync is None else sync.wdk_strategy_id,
        root_wdk_step_id=None if sync is None else sync.wdk_root_step_id,
        node_results=derive_ledger(deps.state, deps.intent).build.node_results,
        spec=deps.state.domain.operational_spec,
        control_tests=deps.state.turn_markers.control_tests,
        verdict=verdict,
    )


async def publish_evidence_card(
    deps: LeadDeps, *, check_id: str, revision: str, verdict: EvidenceVerdict
) -> EvidenceCard:
    """Read the site once, keep the card as the thread's last and stream it."""
    sources = _sources(deps, check_id=check_id, revision=revision, verdict=verdict)
    site = (
        None
        if sources.wdk_strategy_id is None
        else await read_step_counts(sources.site_id, sources.wdk_strategy_id)
    )
    card = assemble_evidence_card(sources, site, checked_at=datetime.now(UTC))
    deps.state.domain.last_evidence_card = card
    emit_chunk(get_stream_writer(), evidence_card_event(card))
    return card


__all__ = ["CardSources", "assemble_evidence_card", "publish_evidence_card"]
