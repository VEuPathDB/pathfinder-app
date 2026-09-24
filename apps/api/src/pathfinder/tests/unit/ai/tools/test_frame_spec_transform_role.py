"""``set_criterion`` matches the role against what the search accepts.

A transform runs on a previous step's results; a seed or filter search runs on
its own. Binding one as the other builds a step WDK refuses.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb_mcp import tool_payloads
from veupathdb_mcp.tool_payloads import TransformListing

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult, set_criterion
from pathfinder.ai.tools.toolsets.frame import _frame_enum_overrides
from pathfinder.domain.strategy.operational_spec import CriterionRole
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    frame_ctx,
    genes_by_text,
    serve_definition,
    serve_search,
)

_LEAF = "GenesByOrthologPattern"
_TRANSFORM = "GenesByOrthologs"

_LISTINGS = [
    TransformListing(
        name=_TRANSFORM,
        display_name="Transform to Orthologs",
        description="The orthologs of the input genes in another organism.",
    ),
    TransformListing(
        name="GenesByWeight",
        display_name="Filter by Weight",
        description="The input genes above a weight.",
    ),
]


def serve_transforms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _listings(_site: str, _record_type: str) -> list[TransformListing]:
        return _LISTINGS

    monkeypatch.setattr(tool_payloads, "list_transform_listings", _listings)


def serve_sheet(monkeypatch: pytest.MonkeyPatch, *, takes_an_input_step: bool) -> None:
    """A search whose definition states whether it accepts a primary input."""
    serve_transforms(monkeypatch)
    serve_definition(
        monkeypatch,
        allowed_primary_input_record_class_names=["transcript"]
        if takes_an_input_step
        else None,
    )


async def open_sheet(
    state: AgentToolState, search_name: str, role: CriterionRole
) -> SetCriterionResult:
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="vivax_orthologs",
            text="P. vivax P01 orthologs",
            search_name=search_name,
            role=role,
        ),
        SetCriterionResult,
    )


@pytest.mark.asyncio
async def test_a_transform_role_on_a_leaf_search_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_sheet(monkeypatch, takes_an_input_step=False)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as exc:
        await open_sheet(state, _LEAF, "transform")

    assert _TRANSFORM in str(exc.value)
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_the_refusal_names_every_transform_of_the_record_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_sheet(monkeypatch, takes_an_input_step=False)

    with pytest.raises(ModelRetry) as exc:
        await open_sheet(AgentToolState(), _LEAF, "transform")

    assert "GenesByWeight" in str(exc.value)


@pytest.mark.asyncio
async def test_a_transform_binds_under_the_transform_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_sheet(monkeypatch, takes_an_input_step=True)

    result = await open_sheet(AgentToolState(), _TRANSFORM, "transform")

    assert result.sheet_pinned is True


@pytest.mark.parametrize("role", ["filter", "seed", "exclude"])
@pytest.mark.asyncio
async def test_a_standalone_role_on_a_transform_is_refused(
    monkeypatch: pytest.MonkeyPatch, role: CriterionRole
) -> None:
    serve_sheet(monkeypatch, takes_an_input_step=True)

    with pytest.raises(ModelRetry) as exc:
        await open_sheet(AgentToolState(), _TRANSFORM, role)

    assert 'role="transform"' in str(exc.value)


@pytest.mark.asyncio
async def test_a_leaf_search_binds_under_a_standalone_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_sheet(monkeypatch, takes_an_input_step=False)

    result = await open_sheet(AgentToolState(), _LEAF, "filter")

    assert result.sheet_pinned is True


@pytest.mark.asyncio
async def test_the_binding_call_refuses_it_too_so_no_spec_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The push only ever sees criteria the spec holds, and this one is refused
    before it is recorded."""
    serve_transforms(monkeypatch)
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as exc:
        await set_criterion(
            frame_ctx(state),
            criterion_id="vivax_orthologs",
            text="P. vivax P01 orthologs",
            search_name=_LEAF,
            role="transform",
            params=dict(KINASE_PARAMS),
        )

    assert _TRANSFORM in str(exc.value)
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_the_refusal_records_the_transforms_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard that names a transform admits it on the next call."""
    serve_sheet(monkeypatch, takes_an_input_step=False)
    state = AgentToolState()
    state.record_catalog_read(listing(["GenesByEcNumber", _LEAF]))

    with pytest.raises(ModelRetry):
        await open_sheet(state, _LEAF, "transform")

    overrides = _frame_enum_overrides(frame_ctx(state))
    assert overrides[("set_criterion", "search_name")] == [
        "GenesByEcNumber",
        _LEAF,
        _TRANSFORM,
        "GenesByWeight",
    ]
    assert overrides[("get_search_overview", "search_name")] == [
        "GenesByEcNumber",
        _LEAF,
        _TRANSFORM,
        "GenesByWeight",
    ]


@pytest.mark.asyncio
async def test_a_saved_strategy_cannot_take_the_transform_role() -> None:
    """A saved strategy is the input a criterion starts from."""
    state = AgentToolState()

    with pytest.raises(ModelRetry) as exc:
        await set_criterion(
            frame_ctx(state),
            criterion_id="saved",
            text="the union I saved",
            role="transform",
            saved_strategy="My union",
        )

    assert 'role="seed"' in str(exc.value)
    assert state.operational_spec_draft.criteria == []
