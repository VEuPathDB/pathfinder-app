"""A separation's literature reference survives only when a read of this message
returned it; the counts it was measured with stay either way."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb_mcp.separation import CandidateSource, SeparationResult

from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.separation import SeparationOffer, SeparationReport
from pathfinder.tests._support.separation import (
    SEPARATION_CALL,
    SIGNAL_PEPTIDE,
    TASK_ID,
    lead_answered_by_a_separation,
    recorded_separation,
)

_DOI = "https://doi.org/10.1038/nature03069"
_READ_AS = "doi:10.1038/nature03069"


class _Resumed(BaseModel):
    """The chunks the resumed call carries to the thread."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    metadata: list[DataChunk]


def _cited() -> SeparationResult:
    """The recorded run, with its first leaf drawn from a paper."""
    result = recorded_separation(SIGNAL_PEPTIDE)
    measured = [
        m.model_copy(
            update={
                "candidate": m.candidate.model_copy(
                    update={
                        "source": CandidateSource.LITERATURE,
                        "basis": "exported proteins",
                        "reference": _DOI,
                    }
                )
            }
        )
        if m.candidate.id == "c4"
        else m
        for m in result.measured
    ]
    return result.model_copy(update={"measured": measured})


def _deps(*, read: bool) -> LeadDeps:
    deps = lead_answered_by_a_separation(_cited())
    if read:
        deps.state.turn_markers.record_retrieved_source(_READ_AS)
    return deps


async def _offer(deps: LeadDeps) -> tuple[SeparationOffer, SeparationReport]:
    resumed = await resolve_turn_resumption(state=deps.state, deps=deps)
    assert resumed.results is not None
    returned = _Resumed.model_validate(resumed.results.calls[SEPARATION_CALL])
    (part,) = [c for c in returned.metadata if c.type == "data-separation-result"]
    report = SeparationReport.model_validate(part.data)
    return deps.state.domain.separation_offers[str(TASK_ID)], report


def _leaf_sources(offer: SeparationOffer) -> tuple[list[str], int, int]:
    chosen = offer.spec.criteria[0].rationale
    assert chosen is not None
    assert chosen.kind == "controls"
    return chosen.sources, chosen.recovered, chosen.admitted


async def test_a_reference_the_message_read_is_kept_in_the_form_it_was_read() -> None:
    offer, report = await _offer(_deps(read=True))

    assert _leaf_sources(offer) == ([_READ_AS], 42, 0)
    assert report.offer == offer
    assert report.measured[0].reference == _READ_AS


async def test_a_reference_the_message_did_not_read_leaves_and_the_counts_stay() -> (
    None
):
    offer, report = await _offer(_deps(read=False))

    assert _leaf_sources(offer) == ([], 42, 0)
    assert report.offer == offer
    assert report.measured[0].reference is None
