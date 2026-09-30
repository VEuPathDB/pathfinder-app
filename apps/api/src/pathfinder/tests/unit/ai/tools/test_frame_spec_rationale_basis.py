"""``set_criterion(why=...)``: each basis is checked against data the call
holds, and a cited reference must be one this turn retrieved."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import SearchMatch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
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
    ("basis", "term", "reason", "message"),
    [
        (
            "parameter",
            "Percentile",
            "sets Percentile to 90",
            (
                "c_gpi: Percentile is not a parameter of GenesByExportPrediction. "
                "With basis parameter the term is the display name of a parameter "
                "this call sets: Organism. A value goes in the reason, never in "
                "the term."
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
                "not hold GPI anchor. They read: Exported Protein; Find genes that "
                "are predicted by ExportPred to produce an exported protein. Pass as "
                "the term a phrase of the request these words hold, or give another "
                "basis."
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


# A reason past its cap is refused with its length; the term is not required in it.

_LONG_TAIL = (
    ", which the request names as the genome to search, and the catalog "
    "answered this search first among the exported-protein searches it ranked"
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "length"),
    [
        (f"sets Organism to P. falciparum 3D7{_LONG_TAIL}", 173),
        (f"sets the genome searched to P. falciparum 3D7{_LONG_TAIL}", 184),
    ],
)
async def test_a_reason_past_its_cap_is_refused_with_its_length(
    monkeypatch: pytest.MonkeyPatch, reason: str, length: int
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(state, choice("parameter", "Organism", reason))

    assert refusal == (
        f"c_gpi: the reason holds {length} characters. Write one line of at most "
        f"160 characters; the term Organism is shown before it. Nothing was "
        f"recorded."
    )


# A term the call holds under another name is recorded under that name.


@pytest.mark.asyncio
async def test_the_organism_value_passed_as_the_term_is_corrected_to_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    result = await choose(
        state,
        choice(
            "parameter", "plasmodium falciparum 3D7", "the request names the genome"
        ),
    )

    assert result.rationale is not None
    assert (result.rationale.term, result.rationale.sentence, result.corrections) == (
        "Organism",
        "Organism: the request names the genome",
        ["why.term corrected to Organism: plasmodium falciparum 3D7 is its value"],
    )


@pytest.mark.asyncio
async def test_the_corrected_organism_term_is_refused_beside_a_set_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(
        state,
        choice("parameter", "Plasmodium falciparum 3D7", "the request names it"),
        params={**PARAMS, "min_exportpred_score": "20"},
    )

    assert refusal == (
        "c_gpi: Organism is the organism the search runs on, and this call also "
        "sets Minimum ExportPred Score, which is what decides the choice. Pass "
        "the term 'Minimum ExportPred Score' with basis parameter, and keep the "
        "organism in the reason."
    )


@pytest.mark.asyncio
async def test_the_search_name_passed_as_the_term_is_its_only_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    result = await choose(
        state,
        choice("parameter", "exported protein", "the request asks for exported ones"),
    )

    assert result.rationale is not None
    assert (result.rationale.basis, result.rationale.term, result.corrections) == (
        "only_match",
        "Exported Protein",
        [
            (
                "why corrected to only_match on Exported Protein: exported "
                "protein names the search, not a parameter"
            )
        ],
    )


_EXPORTOME = match(
    "GenesByExportome",
    "Exportome",
    "Find genes whose exported protein a proteome study detected.",
    0.3,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hits", "params", "set_here"),
    [
        ((EXPORTED, _EXPORTOME), PARAMS, "Organism"),
        (
            (EXPORTED, SIGNAL),
            {**PARAMS, "min_exportpred_score": "20"},
            "Organism, Minimum ExportPred Score",
        ),
    ],
)
async def test_the_search_name_as_the_term_is_refused_when_it_is_no_only_match(
    monkeypatch: pytest.MonkeyPatch,
    hits: tuple[SearchMatch, ...],
    params: dict[str, str | list[str] | None],
    set_here: str,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, *hits)

    refusal = await refused(
        state,
        choice("parameter", "Exported Protein", "the request asks for them"),
        params=params,
    )

    assert refusal == (
        f"c_gpi: Exported Protein is not a parameter of GenesByExportPrediction. "
        f"With basis parameter the term is the display name of a parameter this "
        f"call sets: {set_here}. A value goes in the reason, never in the term."
    )
