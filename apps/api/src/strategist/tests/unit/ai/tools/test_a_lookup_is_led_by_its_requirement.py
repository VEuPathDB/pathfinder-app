from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.tools.standalone import catalog_discovery
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    PropertyValue,
)
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_MESSAGE = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"


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


async def _request_terms(
    monkeypatch: pytest.MonkeyPatch, requirement: str | None
) -> tuple[str, ...]:
    read = AsyncMock(return_value=_param_info("domain_typeahead"))
    monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)
    ctx = agent_run_context()
    ctx.deps.agent_state.request_messages = [_MESSAGE]
    ctx.deps.agent_state.stated_requirements = [
        Constraint(
            kind=ConstraintKind.PROPERTY,
            requested_value="odorant binding",
            label="odorant binding",
            quote="odorant-binding protein",
            source=ConstraintSource.USER_EXPLICIT,
            value=PropertyValue(phrase="odorant binding"),
        )
    ]

    await catalog_discovery.get_parameter_options(
        ctx,
        search_name="GenesByInterproDomain",
        parameter_id="domain_typeahead",
        query=["odorant-binding protein", "pheromone binding"],
        requirement=requirement,
    )

    assert read.await_args is not None
    terms: tuple[str, ...] = read.await_args.kwargs["narrowing"].request_terms
    return terms


async def test_the_request_is_the_linked_requirement_s_quote_and_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terms = await _request_terms(monkeypatch, "R1")

    assert terms == ("odorant-binding protein", "odorant binding")


async def test_a_lookup_that_names_no_requirement_carries_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _request_terms(monkeypatch, None) == ()
