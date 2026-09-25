"""An organism the transform cannot reach, held on another site, earns the portal
route: a new conversation on the portal, never a site switch."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import format_param_info_typed
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    refuse_unmatched_values,
)
from pathfinder.tests._support.recorded_searches import suite_search

_ORTHOLOGS = WDKSearchResponse.model_validate(
    load_recorded("search_genes_by_orthologs").json_body()
).search_data
_INFOS = format_param_info_typed(_ORTHOLOGS.parameters or [])
_TOXO = "Toxoplasma gondii ME49"
_UNMATCHED = (
    "organism on GenesByOrthologs has no entry matching ['Toxoplasma gondii ME49']. "
    "Copy a value or a label from the vocabulary exactly; a substring names a "
    "different entry. Nearest entries: ['Plasmodiidae', 'Plasmodium', "
    "'Plasmodium inui', 'Plasmodium vivax PAM', 'Plasmodium vivax']."
)
_ROUTE = (
    " Transform by Orthology on plasmodb reaches Haemoproteidae and Plasmodiidae; "
    "a transform to Toxoplasma gondii ME49 runs on the VEuPathDB portal, where one "
    "strategy holds both organisms. Toxoplasma gondii ME49 is on toxodb. A "
    "conversation stays on its site: bind nothing for this criterion, ask no "
    "question about it, and write this in the summary word for word, link "
    "included: This needs the VEuPathDB Portal, where one strategy holds both "
    "organisms. [Open a new conversation there](/veupathdb/conversation); this "
    "conversation stays on PlasmoDB."
)


def _call(organism: str) -> CriterionCall:
    return CriterionCall(
        criterion_id="c_to_toxo",
        search_name="GenesByOrthologs",
        text=f"their orthologs in {organism}",
        params={"organism": [organism], "isSyntenic": "no"},
    )


async def _refusal(
    monkeypatch: pytest.MonkeyPatch, holders: AsyncMock, state: AgentToolState
) -> str:
    monkeypatch.setattr(catalog, "sites_holding_organism", holders)
    with pytest.raises(ModelRetry) as refused:
        await refuse_unmatched_values(
            "plasmodb", _ORTHOLOGS, _call(_TOXO), _INFOS, frozenset(), state
        )
    return str(refused.value)


@pytest.mark.asyncio
async def test_an_organism_on_another_site_opens_the_portal_and_asks_no_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holders = AsyncMock(return_value=["toxodb"])
    state = AgentToolState()

    refusal = await _refusal(monkeypatch, holders, state)

    holders.assert_awaited_once_with(_TOXO)
    assert refusal == f"{_UNMATCHED}{_ROUTE}"
    assert "needs_user" not in refusal
    assert state.portal_route == (
        "This needs the VEuPathDB Portal, where one strategy holds both organisms. "
        "[Open a new conversation there](/veupathdb/conversation); this "
        "conversation stays on PlasmoDB."
    )


@pytest.mark.asyncio
async def test_vectorbase_to_plasmodium_links_the_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aedes_orthologs = suite_search("search_genes_by_orthologs_vectorbase")
    monkeypatch.setattr(
        catalog, "sites_holding_organism", AsyncMock(return_value=["plasmodb"])
    )
    call = CriterionCall(
        criterion_id="c_to_pf",
        search_name="GenesByOrthologs",
        text="their orthologs in Plasmodium falciparum 3D7",
        params={"organism": ["Plasmodium falciparum 3D7"], "isSyntenic": "no"},
    )

    with pytest.raises(ModelRetry) as refused:
        await refuse_unmatched_values(
            "vectorbase",
            aedes_orthologs,
            call,
            format_param_info_typed(aedes_orthologs.parameters or []),
            frozenset(),
            AgentToolState(),
        )

    assert str(refused.value).endswith(
        " Transform by Orthology on vectorbase reaches Arthropoda and Mollusca; a "
        "transform to Plasmodium falciparum 3D7 runs on the VEuPathDB portal, where "
        "one strategy holds both organisms. Plasmodium falciparum 3D7 is on "
        "plasmodb. A conversation stays on its site: bind nothing for this "
        "criterion, ask no question about it, and write this in the summary word "
        "for word, link included: This needs the VEuPathDB Portal, where one "
        "strategy holds both organisms. [Open a new conversation "
        "there](/veupathdb/conversation); this conversation stays on VectorBase."
    )


@pytest.mark.asyncio
async def test_an_organism_no_other_site_holds_earns_the_plain_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState()

    refusal = await _refusal(monkeypatch, AsyncMock(return_value=["plasmodb"]), state)

    assert refusal == _UNMATCHED
    assert state.portal_route == ""


@pytest.mark.asyncio
async def test_an_index_that_does_not_answer_earns_the_plain_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = AsyncMock(side_effect=SemanticIndexUnavailableError("store down"))

    refusal = await _refusal(monkeypatch, down, AgentToolState())

    assert refusal == _UNMATCHED


@pytest.mark.asyncio
async def test_a_flat_vocabulary_asks_no_site(monkeypatch: pytest.MonkeyPatch) -> None:
    holders = AsyncMock(return_value=["toxodb"])
    monkeypatch.setattr(catalog, "sites_holding_organism", holders)
    call = CriterionCall(
        criterion_id="c_to_pviv",
        search_name="GenesByOrthologs",
        text="syntenic orthologs in Plasmodium vivax P01",
        params={"organism": ["Plasmodium vivax P01"], "isSyntenic": "maybe"},
    )

    with pytest.raises(ModelRetry) as refused:
        await refuse_unmatched_values(
            "plasmodb", _ORTHOLOGS, call, _INFOS, frozenset(), AgentToolState()
        )

    assert str(refused.value) == (
        "isSyntenic on GenesByOrthologs has no entry matching ['maybe']. Copy a "
        "value or a label from the vocabulary exactly; a substring names a "
        "different entry. Nearest entries: ['yes', 'no']."
    )
    holders.assert_not_awaited()
