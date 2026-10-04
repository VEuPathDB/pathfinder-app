"""What a turn read and moved, as its facts part shows it: each record and each
listed id under the step whose listing gave it, the genes the gate resolved,
and each count this turn's writes moved beside the count the message found."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.graph.turn_records import ReadRecord, TurnMarkers
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.domain.turn_facts import ListedFact, SourceFact, StepFact
from pathfinder.services.gene_records.read import gene_record_url


def with_counts_before(
    steps: Sequence[StepFact], markers: TurnMarkers
) -> list[StepFact]:
    """Each step with the count it held when the message arrived, where this
    turn's writes moved it."""
    return [
        s.model_copy(update={"count_before": markers.count_before(s.step_id, s.count)})
        for s in steps
    ]


def _gene(record: ReadRecord) -> SourceFact:
    return SourceFact(
        url=record.url,
        record_id=record.record_id,
        product=record.product,
        organism=record.organism,
        values=record.words(),
    )


def _step_of(sync: SyncStateProtocol | None) -> dict[int, str]:
    return {} if sync is None else {w: s for s, w in sync.wdk_step_ids.items()}


def read_sources(
    markers: TurnMarkers,
    steps: Sequence[StepFact],
    sync: SyncStateProtocol | None,
    review: VerificationReview | None,
) -> list[SourceFact]:
    """Every record this turn read, under the step whose listing gave it and with
    the check's judgement of it, then every other reference it retrieved. A
    record a step the strategy no longer holds listed is no source."""
    step_of = _step_of(sync)
    named = {step.step_id: step.display_name for step in steps}
    judged = {} if review is None else {g.gene_id: g for g in review.sampled_genes}
    records: list[SourceFact] = []
    for record in markers.records_retrieved:
        listed = markers.listed_from(record.record_id)
        step_id = "" if listed is None else step_of.get(listed, "")
        if listed is not None and step_id not in named:
            continue
        gene = judged.get(record.record_id)
        records.append(
            _gene(record).model_copy(
                update={
                    "step_id": step_id,
                    "step_name": named.get(step_id, ""),
                    "fit": None if gene is None else gene.fits,
                    "why": "" if gene is None else gene.why,
                }
            )
        )
    pages = {record.url for record in markers.records_retrieved}
    return [
        *records,
        *(SourceFact(url=u) for u in markers.retrieved_sources if u not in pages),
    ]


def listed_ids(
    site_id: str,
    markers: TurnMarkers,
    steps: Sequence[StepFact],
    sync: SyncStateProtocol | None,
    sources: Sequence[SourceFact],
) -> list[ListedFact]:
    """The ids each listing of this turn returned, each with its record page,
    under the step it listed, in tree order. A record shown as a source of that
    step is not listed again, and a listing of a step the strategy no longer
    holds is no fact."""
    step_of = _step_of(sync)
    shown = {(source.step_id, source.record_id) for source in sources}
    listed: dict[str, list[str]] = {}
    for wdk_step_id, genes in markers.listings.items():
        step_id = step_of.get(wdk_step_id, "")
        held = listed.setdefault(step_id, [])
        held.extend(g for g in genes if (step_id, g) not in shown and g not in held)
    return [
        ListedFact(
            step_id=step.step_id,
            step_name=step.display_name,
            records=[
                ListedRecord(record_id=g, url=gene_record_url(site_id, g))
                for g in listed[step.step_id]
            ],
        )
        for step in steps
        if listed.get(step.step_id)
    ]


def named_genes(markers: TurnMarkers) -> list[SourceFact]:
    """The genes the message names that the gate resolved to the site's records."""
    return [_gene(record) for record in markers.resolved_genes]


__all__ = ["listed_ids", "named_genes", "read_sources", "with_counts_before"]
