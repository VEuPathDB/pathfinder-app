"""A lookup ranks first the phrasings a request message states."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _param_info(name: str) -> ParameterInfo:
    return ParameterInfo.model_validate(
        {
            "name": name,
            "display_name": "Domain",
            "type": "string",
            "required": True,
            "is_visible": True,
            "help": "",
            "value_format": "",
        }
    )


class TestTheRequestsOwnPhrasingsRankFirst:
    """The phrasings the request writes out travel as its own words."""

    async def test_only_a_phrasing_a_request_message_states_is_the_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        read = AsyncMock(return_value=_param_info("domain_typeahead"))
        monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)
        ctx = agent_run_context()
        ctx.deps.agent_state.request_messages = [
            "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"
        ]

        await catalog_discovery.get_parameter_options(
            ctx,
            search_name="GenesByInterproDomain",
            parameter_id="domain_typeahead",
            query=[
                "odorant-binding protein",
                "pheromone binding",
                "insect pheromone-binding",
            ],
        )

        assert read.await_args is not None
        narrowing = read.await_args.kwargs["narrowing"]
        assert narrowing.request_terms == ("odorant-binding protein",)

    async def test_a_query_the_request_never_writes_ranks_nothing_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        read = AsyncMock(return_value=_param_info("domain_typeahead"))
        monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)
        ctx = agent_run_context()
        ctx.deps.agent_state.request_messages = ["kinases on chromosome 3"]

        await catalog_discovery.get_parameter_options(
            ctx,
            search_name="GenesByInterproDomain",
            parameter_id="domain_typeahead",
            query=["pheromone binding"],
        )

        assert read.await_args is not None
        assert read.await_args.kwargs["narrowing"].request_terms == ()
