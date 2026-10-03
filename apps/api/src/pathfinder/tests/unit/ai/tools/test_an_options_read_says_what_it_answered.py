"""``get_parameter_options`` writes a trace line for each kind of answer, and a
read a query narrowed holds the entries it matched as a lookup of that
parameter this pass."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParameterNotOnSearch,
    ParentContextRequired,
    PhrasingMatch,
    VocabLookup,
)

from pathfinder.ai.agents.state import AgentToolState, LookupRecord
from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of

_INTERPRO = "GenesByInterproDomain"
_DOMAINS = "domain_typeahead"


def _answering(
    monkeypatch: pytest.MonkeyPatch,
    answer: ParameterInfo | ParameterNotOnSearch | ParentContextRequired,
) -> None:
    monkeypatch.setattr(
        catalog_discovery, "read_parameter_options", AsyncMock(return_value=answer)
    )


async def _summary(
    state: AgentToolState, query: list[str] | None = None
) -> dict[str, str]:
    returned = await catalog_discovery.get_parameter_options(
        agent_run_context(agent_state=state),
        search_name=_INTERPRO,
        parameter_id=_DOMAINS,
        query=query,
    )
    return TypeAdapter(dict[str, str]).validate_python(summary_of(returned).data)


def _domains(lookup: VocabLookup | None) -> ParameterInfo:
    return ParameterInfo(
        name=_DOMAINS,
        display_name="Specific Domain(s)",
        type="multi-pick-vocabulary",
        required=True,
        is_visible=True,
        help="",
        value_format="",
        allowed_values=[
            VocabOption(value="PF01395", display="PF01395 : PBP/GOBP family")
        ],
        vocab_lookup=lookup,
    )


async def test_a_parent_context_answer_names_the_parents_it_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answering(
        monkeypatch,
        ParentContextRequired(
            search_name=_INTERPRO,
            parameter_id=_DOMAINS,
            parent_parameter_ids=["domain_database", "organism"],
            message="bind the parents first",
        ),
    )

    data = await _summary(AgentToolState())

    assert (data["summary"], data["status"]) == (
        "domain_typeahead needs domain_database and organism first",
        "warn",
    )


async def test_a_parameter_the_search_lacks_is_not_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answering(
        monkeypatch,
        ParameterNotOnSearch(
            search_name=_INTERPRO,
            requested_parameter_id=_DOMAINS,
            message="no such parameter",
            suggestions=[],
            valid_parameter_ids=["organism"],
        ),
    )

    data = await _summary(AgentToolState())

    assert data["summary"] == f"{_DOMAINS} is not on {_INTERPRO}"


async def test_a_read_a_query_narrowed_holds_the_entries_it_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = VocabLookup(
        terms=["PBP/GOBP"],
        matches=[
            PhrasingMatch(
                term="PBP/GOBP",
                phrasing="pbp gobp",
                reach="phrase",
                values=["PF01395"],
            )
        ],
    )
    _answering(monkeypatch, _domains(lookup))
    state = AgentToolState()

    await _summary(state, query=["PBP/GOBP"])

    assert state.looked_up == {
        (_INTERPRO, _DOMAINS): LookupRecord(matched={"PF01395": "PBP/GOBP"})
    }


async def test_a_read_with_no_query_is_no_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answering(monkeypatch, _domains(None))
    state = AgentToolState()

    await _summary(state)

    assert state.looked_up == {}
