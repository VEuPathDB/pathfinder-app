"""An organism the transform cannot reach, held on another site, earns the portal
route: a new conversation on the portal, never a site switch."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.wdk import WDKParameter, WDKSearch, WDKSearchResponse
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ResolveContext
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from strategist.ai.agents.state import AgentToolState
from strategist.ai.lead.site_routes import portal_route_sentence
from strategist.ai.tools.standalone._frame_proposals import CriterionCall, read_call
from strategist.tests._support.qa_recording import client_recording
from strategist.tests._support.recorded_searches import suite_search

_ORTHOLOGS = WDKSearchResponse.model_validate(
    client_recording("search_genes_by_orthologs").json_body()
).search_data
_TOXO = "Toxoplasma gondii ME49"
_UNMATCHED = f"organism has no entry {_TOXO!r}. Candidates: "
_RECORDED = " Nothing was recorded."
_ROUTE = (
    " Transform by Orthology on plasmodb reaches Haemoproteidae and Plasmodiidae; "
    "a transform to Toxoplasma gondii ME49 runs on the VEuPathDB portal, where one "
    "strategy holds both organisms. Toxoplasma gondii ME49 is on toxodb. A "
    "conversation stays on its site: bind nothing for this criterion, ask no "
    "question about it, and write this in the summary word for word, link "
    "included: This needs the VEuPathDB Portal, where one strategy holds both "
    "organisms. [Open a new conversation "
    "there](https://qa.veupathdb.org/veupathdb.qa/app/strategist/conversation); this conversation stays on "
    "PlasmoDB. Save the result there as a gene set, and a conversation on PlasmoDB "
    "can start from its PlasmoDB genes."
)


async def _read(
    site_id: str,
    definition: WDKSearch,
    params: dict[str, JsonValue],
    state: AgentToolState,
) -> str:
    async def fetch_at(_context: dict[str, str]) -> list[WDKParameter]:
        return list(definition.parameters or [])

    call = CriterionCall(
        criterion_id="c_orthologs",
        search_name="GenesByOrthologs",
        text="their orthologs",
        params=params,
    )
    with pytest.raises(ModelRetry) as refused:
        await read_call(
            SearchContext(site_id, "transcript", "GenesByOrthologs"),
            fetch_at,
            call,
            definition=definition,
            state=state,
            about=ResolveContext(site_id=site_id),
        )
    return str(refused.value)


async def _refusal(
    monkeypatch: pytest.MonkeyPatch, holders: AsyncMock, state: AgentToolState
) -> str:
    monkeypatch.setattr(catalog, "sites_holding_organism", holders)
    return await _read(
        "plasmodb", _ORTHOLOGS, {"organism": [_TOXO], "isSyntenic": "no"}, state
    )


@pytest.mark.asyncio
async def test_an_organism_on_another_site_opens_the_portal_and_asks_no_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holders = AsyncMock(return_value=["toxodb"])
    state = AgentToolState()

    refusal = await _refusal(monkeypatch, holders, state)

    holders.assert_awaited_once_with(_TOXO)
    assert refusal.startswith(_UNMATCHED)
    assert refusal.endswith(f"{_ROUTE}{_RECORDED}")
    assert "needs_user" not in refusal
    assert state.portal_route == (
        "This needs the VEuPathDB Portal, where one strategy holds both organisms. "
        "[Open a new conversation there](https://qa.veupathdb.org/veupathdb.qa/app/strategist/conversation); this "
        "conversation stays on PlasmoDB. Save the result there as a gene set, and a "
        "conversation on PlasmoDB can start from its PlasmoDB genes."
    )


def test_the_portal_link_stays_under_the_base_path() -> None:
    sentence = portal_route_sentence("plasmodb")

    assert (
        "(https://qa.veupathdb.org/veupathdb.qa/app/strategist/conversation)"
        in sentence
    )


@pytest.mark.asyncio
async def test_vectorbase_to_plasmodium_links_the_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aedes_orthologs = suite_search("search_genes_by_orthologs_vectorbase")
    monkeypatch.setattr(
        catalog, "sites_holding_organism", AsyncMock(return_value=["plasmodb"])
    )
    refusal = await _read(
        "vectorbase",
        aedes_orthologs,
        {"organism": ["Plasmodium falciparum 3D7"], "isSyntenic": "no"},
        AgentToolState(),
    )

    assert refusal.endswith(
        " Transform by Orthology on vectorbase reaches Arthropoda and Mollusca; a "
        "transform to Plasmodium falciparum 3D7 runs on the VEuPathDB portal, where "
        "one strategy holds both organisms. Plasmodium falciparum 3D7 is on "
        "plasmodb. A conversation stays on its site: bind nothing for this "
        "criterion, ask no question about it, and write this in the summary word "
        "for word, link included: This needs the VEuPathDB Portal, where one "
        "strategy holds both organisms. [Open a new conversation "
        "there](https://qa.veupathdb.org/veupathdb.qa/app/strategist/conversation); this conversation stays on "
        "VectorBase. Save the result there as a gene set, and a conversation on "
        "VectorBase can start from its VectorBase genes. Nothing was recorded."
    )


@pytest.mark.asyncio
async def test_an_organism_no_other_site_holds_earns_the_plain_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()

    refusal = await _refusal(monkeypatch, AsyncMock(return_value=["plasmodb"]), state)

    assert refusal.startswith(_UNMATCHED)
    assert refusal.endswith(f". {_RECORDED.strip()}")
    assert "portal" not in refusal
    assert state.portal_route == ""


@pytest.mark.asyncio
async def test_an_index_that_does_not_answer_earns_the_plain_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = AsyncMock(side_effect=SemanticIndexUnavailableError("store down"))

    refusal = await _refusal(monkeypatch, down, AgentToolState())

    assert refusal.startswith(_UNMATCHED)
    assert "portal" not in refusal


@pytest.mark.asyncio
async def test_a_flat_vocabulary_asks_no_site(monkeypatch: pytest.MonkeyPatch) -> None:
    holders = AsyncMock(return_value=["toxodb"])
    monkeypatch.setattr(catalog, "sites_holding_organism", holders)
    refusal = await _read(
        "plasmodb",
        _ORTHOLOGS,
        {"organism": ["Plasmodium vivax P01"], "isSyntenic": "maybe"},
        AgentToolState(),
    )

    assert refusal.startswith("isSyntenic has no entry 'maybe'. Candidates: ")
    assert refusal.endswith(_RECORDED)
    holders.assert_not_awaited()
