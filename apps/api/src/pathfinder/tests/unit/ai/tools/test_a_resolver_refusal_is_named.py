from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import (
    HiddenParameterError,
    PhyleticListError,
    ResolvedParams,
    resolve_params_with_intent,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_proposals
from pathfinder.tests.unit.ai.tools.test_frame_proposals import (
    PHYLETIC_ORGANISM,
    propose,
    serve_for,
)


@pytest.mark.asyncio
async def test_a_phyletic_list_error_is_a_named_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = AgentToolState()

    async def _resolve(**_kw: object) -> ResolvedParams:
        raise PhyleticListError(None)

    serve_for(monkeypatch, "GenesByOptionalPercentile")
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _resolve)

    with pytest.raises(ModelRetry) as exc:
        await propose(
            st, "GenesByOptionalPercentile", {"min_expression_percentile": "90"}
        )

    assert str(exc.value) == (
        "GenesByOptionalPercentile: profile_pattern is derived from "
        "included_species and excluded_species against the search's published "
        "parameters, and the call passed none. A genus or common name is not a "
        "node: name a species or a clade code from the included_species / "
        "excluded_species vocabulary on the sheet, or call "
        "lookup_phyletic_codes(query). Nothing was recorded."
    )
    assert st.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_a_hidden_parameter_error_is_a_named_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = AgentToolState()

    async def _resolve(**_kw: object) -> ResolvedParams:
        name = "channel"
        raise HiddenParameterError(name, unset=True)

    serve_for(monkeypatch, "GenesByOptionalPercentile")
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _resolve)

    with pytest.raises(ModelRetry) as exc:
        await propose(
            st, "GenesByOptionalPercentile", {"min_expression_percentile": "90"}
        )

    assert str(exc.value) == (
        "GenesByOptionalPercentile: channel is a hidden parameter with no value "
        "the site sets, so the search cannot run from the values given. Nothing "
        "was recorded."
    )
    assert st.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_the_resolver_derives_the_pattern_from_both_lists_and_the_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _resolve(**kwargs: Any) -> ResolvedParams:
        captured.update(kwargs)
        return await resolve_params_with_intent(**kwargs)

    serve_for(monkeypatch, "GenesByOrthologPattern")
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _resolve)

    await propose(
        AgentToolState(),
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": "pfal"},
    )

    overrides = captured["overrides"]
    assert isinstance(overrides, dict)
    assert (
        overrides["included_species"],
        "excluded_species" in overrides,
        "profile_pattern" in overrides,
    ) == ("pfal", False, False)
    assert captured["definition"]
