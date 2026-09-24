"""``set_criterion(why=...)``: the choice is recorded against what the catalog
answered, and a reason the read does not back is refused."""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.step_rationale import ComparedSearch, SearchRationale
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    MEMBRANE,
    NEAREST,
    ORGANISM,
    PARAMS,
    QUERY,
    SIGNAL,
    choice,
    choose,
    read,
    refused,
    serve_site,
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_site(monkeypatch)


# The binding records the alternatives it saw.


@pytest.mark.asyncio
async def test_a_binding_records_what_the_catalog_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL, MEMBRANE)

    result = await choose(state, NEAREST)

    chosen = SearchRationale(
        search_name="GenesByExportPrediction",
        basis="nearest",
        term="GPI anchor",
        reason="no search states a GPI anchor; Exported Protein scored nearest",
        similarity=0.44,
        compared=[
            ComparedSearch(
                name="GenesWithSignalPeptide",
                display_name="Predicted Signal Peptide",
                similarity=0.41,
            ),
            ComparedSearch(
                name="GenesByTransmembraneDomains",
                display_name="Transmembrane Domain Count",
                similarity=0.36,
            ),
            ComparedSearch(name="GenesByText", display_name="Gene Text Search"),
        ],
        answered=4,
        query=QUERY,
        tool_call_id="call_read",
    )
    assert (result.rationale, state.operational_spec_draft.criteria[0].rationale) == (
        chosen,
        chosen,
    )


@pytest.mark.asyncio
async def test_the_newest_read_answering_the_search_is_the_one_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)
    await read(monkeypatch, state, SIGNAL, call="call_later", query="signal")
    await read(monkeypatch, state, EXPORTED, call="call_newest", query="exported")

    result = await choose(state, NEAREST)

    assert result.rationale is not None
    assert (result.rationale.tool_call_id, result.rationale.query) == (
        "call_newest",
        "exported",
    )


@pytest.mark.asyncio
async def test_a_listing_records_no_comparison() -> None:
    state = AgentToolState()
    state.record_catalog_read(listing([EXPORTED.name, "GenesByTaxon"]))

    result = await choose(state, ORGANISM)

    assert result.rationale is not None
    assert (
        result.rationale.compared,
        result.rationale.similarity,
        result.rationale.query,
        result.rationale.term,
    ) == ([], None, "", "Organism")


@pytest.mark.asyncio
async def test_a_value_edit_keeps_the_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)
    first = await choose(state, NEAREST)
    edit = AgentToolState(
        operational_spec_draft=state.operational_spec_draft.model_copy(deep=True)
    )

    result = await choose(
        edit, None, params=PARAMS | {"organism": ["Plasmodium vivax P01"]}
    )

    assert (result.resolved_params["organism"], result.rationale) == (
        '["Plasmodium vivax P01"]',
        first.rationale,
    )


@pytest.mark.asyncio
async def test_a_rebinding_replaces_the_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)
    await choose(state, NEAREST)

    result = await choose(
        state,
        choice("only_match", "signal peptide", "only it names a signal peptide"),
        search_name=SIGNAL.name,
    )

    assert result.rationale is not None
    assert (result.rationale.search_name, result.rationale.basis) == (
        "GenesWithSignalPeptide",
        "only_match",
    )


# A rationale naming an unseen search is refused.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "named",
    ["Phenotype Text", "GenesByPhenotypeText"],
)
async def test_a_reason_naming_a_search_the_catalog_did_not_answer_is_refused(
    monkeypatch: pytest.MonkeyPatch, named: str
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)
    why = choice("nearest", "GPI anchor", f"nearer to a GPI anchor than {named}")

    refusal = await refused(state, why)

    assert (named in refusal, "Predicted Signal Peptide" in refusal) == (True, True)


@pytest.mark.asyncio
async def test_a_reason_naming_a_one_word_display_name_is_not_a_mention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED)

    result = await choose(
        state, choice("parameter", "organism", "its Organism parameter holds 3D7")
    )

    assert result.rationale is not None
    assert result.rationale.reason == "its Organism parameter holds 3D7"


@pytest.mark.asyncio
async def test_a_new_binding_no_read_answered_is_refused() -> None:
    refusal = await refused(AgentToolState(), NEAREST)

    assert "search_for_searches" in refusal


@pytest.mark.asyncio
async def test_a_new_binding_without_a_why_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL, MEMBRANE)

    refusal = await refused(state, None)

    assert [
        word in refusal
        for word in ("why", "nearest", "only_match", "Predicted Signal Peptide")
    ] == [True, True, True, True]


@pytest.mark.asyncio
async def test_a_reason_without_its_term_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(
        state, choice("nearest", "GPI anchor", "it scored the highest of them")
    )

    assert "GPI anchor" in refusal
