"""``set_criterion(why=...)``: each basis is checked against data the call
holds, and a cited reference must be one this turn retrieved."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    MEMBRANE,
    NEAREST,
    ORGANISM,
    PARAMS,
    PATHWAY,
    SIGNAL,
    WORDS,
    choice,
    choose,
    match,
    read,
    refused,
    serve_site,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import frame_ctx


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_site(monkeypatch)


# Each basis is checked against data the call holds.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("why", "short"),
    [
        (ORGANISM, "sets Organism"),
        (
            choice(
                "organism",
                "Plasmodium falciparum 3D7",
                "covers Plasmodium falciparum 3D7",
            ),
            "covers Plasmodium falciparum 3D7",
        ),
        (
            choice("only_match", "exported", "only it finds an exported protein"),
            "only search naming exported",
        ),
        (NEAREST, "nearest to GPI anchor"),
    ],
)
async def test_a_basis_the_data_backs_is_recorded(
    monkeypatch: pytest.MonkeyPatch, why: SearchChoice, short: str
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL, MEMBRANE)

    result = await choose(state, why)

    assert result.rationale is not None
    assert result.rationale.short == short


@pytest.mark.asyncio
async def test_a_record_type_no_other_hit_returns_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, PATHWAY)

    result = await choose(
        state, choice("record_type", "transcript", "returns transcript records")
    )

    assert result.rationale is not None
    assert result.rationale.short == "returns transcript"


@pytest.mark.asyncio
async def test_a_record_type_named_as_the_site_shows_it_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, PATHWAY)

    result = await choose(state, choice("record_type", "genes", "returns genes"))

    assert result.rationale is not None
    assert result.rationale.short == "returns genes"


# The references FRAME read before it bound.


@pytest.mark.asyncio
async def test_a_source_this_turn_retrieved_is_recorded_as_retrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED)
    ctx = frame_ctx(state)
    ctx.deps.turn_markers.record_retrieved_source(
        "https://doi.org/10.1016/j.cell.2008.01.001"
    )
    why = NEAREST.model_copy(update={"sources": ["doi:10.1016/j.cell.2008.01.001"]})

    result = returned(
        await set_criterion(
            ctx,
            criterion_id="c_gpi",
            text=WORDS,
            search_name=EXPORTED.name,
            params=dict(PARAMS),
            why=why,
        ),
        SetCriterionResult,
    )

    assert result.rationale is not None
    assert result.rationale.sources == ["https://doi.org/10.1016/j.cell.2008.01.001"]


@pytest.mark.asyncio
async def test_a_source_this_turn_never_retrieved_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED)
    why = NEAREST.model_copy(update={"sources": ["PMID:18267088"]})

    refusal = await refused(state, why)

    assert "PMID:18267088" in refusal


# A reason past its cap is refused with its length; the term is not required in it.

_LONG_TAIL = (
    ", which the request names as the genome to search, and the catalog "
    "answered this search first among the exported-protein searches it ranked"
)


# A term the call holds under another name is recorded under that name.


_EXPORTOME = match(
    "GenesByExportome",
    "Exportome",
    "Find genes whose exported protein a proteome study detected.",
    0.3,
)
