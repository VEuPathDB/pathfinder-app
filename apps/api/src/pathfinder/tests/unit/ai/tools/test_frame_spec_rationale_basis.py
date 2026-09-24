"""``set_criterion(why=...)``: each basis is checked against data the call
holds, and a cited reference must be one this turn retrieved."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult, set_criterion
from pathfinder.tests._support.catalog_reads import listing
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
    ("basis", "term", "reason", "message"),
    [
        (
            "parameter",
            "Percentile",
            "sets Percentile to 90",
            (
                "c_gpi: Percentile is not a parameter of GenesByExportPrediction; "
                "its sheet holds organism, min_exportpred_score."
            ),
        ),
        (
            "parameter",
            "min_exportpred_score",
            "sets min_exportpred_score",
            (
                "c_gpi: this call leaves min_exportpred_score null, so it decides "
                "nothing. Name the parameter whose value decides the choice."
            ),
        ),
        (
            "organism",
            "Toxoplasma gondii",
            "covers Toxoplasma gondii",
            (
                "c_gpi: no value this binding sends holds Toxoplasma gondii, so the "
                "organism does not decide the choice."
            ),
        ),
        (
            "record_type",
            "transcript",
            "returns transcript records",
            (
                "c_gpi: every search the catalog answered returns transcript, so "
                "the record type decides nothing. Give the basis that does."
            ),
        ),
        (
            "record_type",
            "pathway",
            "returns pathway records",
            "c_gpi: GenesByExportPrediction returns transcript, not pathway.",
        ),
        (
            "only_match",
            "predicted",
            "only it says predicted",
            (
                "c_gpi: Predicted Signal Peptide also name predicted, so it is not "
                "the only match."
            ),
        ),
        (
            "only_match",
            "GPI anchor",
            "only it names a GPI anchor",
            (
                "c_gpi: the name and the description of GenesByExportPrediction do "
                "not hold GPI anchor."
            ),
        ),
    ],
)
async def test_a_basis_the_data_does_not_back_is_refused(
    monkeypatch: pytest.MonkeyPatch, basis: str, term: str, reason: str, message: str
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(state, choice(basis, term, reason))

    assert refusal == message


@pytest.mark.asyncio
async def test_nearest_is_refused_when_another_hit_scored_higher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(
        state,
        choice(
            "nearest",
            "GPI anchor",
            "Predicted Signal Peptide is nearest to a GPI anchor",
        ),
        search_name=SIGNAL.name,
    )

    assert "Exported Protein" in refusal


@pytest.mark.asyncio
async def test_nearest_is_refused_on_a_listing() -> None:
    state = AgentToolState()
    state.record_catalog_read(listing([EXPORTED.name]))

    refusal = await refused(state, NEAREST)

    assert "search_for_searches" in refusal


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
