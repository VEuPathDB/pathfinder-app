"""The own-site answer is the list's prefix, and other sites' experiments follow it."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import AsyncMock

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, Field
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ExperimentMatch, SearchMatch
from veupathdb_mcp.embeddings import SemanticIndexUnavailableError

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.catalog import search_for_searches
from pathfinder.tests._support.experiment_cards import CRYPTO, TOXO
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_QUERY = "sporozoite RNA-Seq time course"
_NOTE = (
    "Experiments on other VEuPathDB sites. None can be bound on plasmodb. Read one "
    "with read_experiment to name a condition, a stage or an organism in a search "
    "on plasmodb."
)


class _Shown(BaseModel):
    dataset_id: str = Field(alias="datasetId")


class _Block(BaseModel):
    experiments: list[_Shown]


class _OtherSites(BaseModel):
    other_sites: _Block = Field(alias="otherSites")


def _match(name: str, display_name: str, similarity: float) -> SearchMatch:
    return SearchMatch(
        name=name,
        display_name=display_name,
        description=f"Find genes by {display_name}",
        record_type="transcript",
        relevance=1.0,
        semantic_similarity=similarity,
    )


_OWN = [
    _match("GenesByRNASeqpfal3D7_Su_strand_specific_RSRC", "Sporozoite RNA-Seq", 0.61),
    _match("GenesByExportPred", "Exported Protein", 0.42),
]


def _serve(
    monkeypatch: pytest.MonkeyPatch, elsewhere: Sequence[ExperimentMatch]
) -> AsyncMock:
    monkeypatch.setattr(catalog, "search_for_searches", AsyncMock(return_value=_OWN))
    ranked = AsyncMock(return_value=list(elsewhere))
    monkeypatch.setattr(catalog, "rank_experiments_elsewhere", ranked)
    monkeypatch.setattr(catalog, "get_raw_searches", AsyncMock(return_value=[]))
    return ranked


async def _answer(state: AgentToolState) -> list[JSONObject]:
    ctx = agent_run_context(agent_state=state)
    return returned(await search_for_searches(ctx, query=_QUERY), list[JSONObject])


async def _own_site_answer(monkeypatch: pytest.MonkeyPatch) -> list[JSONObject]:
    _serve(monkeypatch, [])
    return await _answer(AgentToolState())


@pytest.mark.asyncio
async def test_the_own_site_list_is_the_prefix_and_other_sites_follow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = await _own_site_answer(monkeypatch)
    ranked = _serve(monkeypatch, [CRYPTO, TOXO])

    answer = await _answer(AgentToolState())

    ranked.assert_awaited_once_with("plasmodb", _QUERY)
    assert answer[: len(today)] == today
    assert answer[len(today) :] == [
        {
            "otherSites": {
                "note": _NOTE,
                "experiments": [
                    {
                        "site": "cryptodb",
                        "datasetId": "DS_63b0de882c",
                        "similarity": 0.52,
                        "line": (
                            "cryptodb | Cryptosporidium parvum Iowa II | RNASeq | "
                            "Transcriptome of 48 hours in vitro infection "
                            "(Isaza et al.)"
                        ),
                    },
                    {
                        "site": "toxodb",
                        "datasetId": "DS_0d220fc0c6",
                        "similarity": 0.41,
                        "line": (
                            "toxodb | Toxoplasma gondii ME49 | RNASeq | Mouse brain "
                            "bradyzoite transcriptomes at 28, 90, 120 days post "
                            "infection (Garfoot et al.)"
                        ),
                    },
                ],
            }
        }
    ]


@pytest.mark.asyncio
async def test_no_other_site_entry_is_a_hit_of_the_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, [CRYPTO, TOXO])
    state = AgentToolState()

    await _answer(state)

    assert [hit.name for hit in state.catalog_reads[-1].hits] == [
        "GenesByRNASeqpfal3D7_Su_strand_specific_RSRC",
        "GenesByExportPred",
        "GenesByText",
    ]
    assert state.candidate_search_names() == {
        "GenesByRNASeqpfal3D7_Su_strand_specific_RSRC",
        "GenesByExportPred",
        "GenesByText",
    }


@pytest.mark.asyncio
async def test_a_dataset_shown_once_is_not_shown_by_the_next_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = await _own_site_answer(monkeypatch)
    state = AgentToolState()
    _serve(monkeypatch, [CRYPTO])
    await _answer(state)
    _serve(monkeypatch, [TOXO, CRYPTO])

    answer = await _answer(state)

    assert len(answer) == len(today) + 1
    block = _OtherSites.model_validate(answer[-1]).other_sites
    assert [shown.dataset_id for shown in block.experiments] == ["DS_0d220fc0c6"]
    assert list(state.elsewhere) == ["DS_63b0de882c", "DS_0d220fc0c6"]


@pytest.mark.asyncio
async def test_a_pass_that_saw_every_ranked_dataset_answers_as_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = await _own_site_answer(monkeypatch)
    state = AgentToolState()
    _serve(monkeypatch, [CRYPTO])
    await _answer(state)

    assert await _answer(state) == today


@pytest.mark.asyncio
async def test_an_unavailable_index_leaves_the_list_as_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = await _own_site_answer(monkeypatch)
    monkeypatch.setattr(
        catalog,
        "rank_experiments_elsewhere",
        AsyncMock(side_effect=SemanticIndexUnavailableError("store down")),
    )
    state = AgentToolState()

    assert await _answer(state) == today
    assert state.elsewhere == {}


@pytest.mark.asyncio
async def test_the_summary_names_the_other_sites_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, [CRYPTO, TOXO])
    ctx = agent_run_context(agent_state=AgentToolState())

    chunk = summary_of(await search_for_searches(ctx, query=_QUERY))

    assert chunk.data["summary"] == "2 searches, experiments on cryptodb and toxodb"
