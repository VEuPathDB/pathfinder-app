"""A word the bound search's own name states asks for that search, not for one
of its parameters.

Transform by Orthology states "ortholog" in its name, so "orthologs" binds it
at the site's synteny default; "syntenic" is stated only by a parameter and
still holds that parameter to "yes". The definition is the one toxodb
published.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    frame_ctx,
    no_validation,
    serve_params,
    serve_site_listing,
)

_TRANSFORM = "GenesByOrthologs"
_NEOSPORA = "Neospora caninum Liverpool"
_ORTHOLOGS = suite_search("search_genes_by_orthologs_toxodb")


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_ORTHOLOGS])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_ORTHOLOGS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _state() -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_orthology",
            tool="list_transforms",
            record_type="transcript",
            query="",
            hits=[
                CatalogHit(
                    name=_TRANSFORM,
                    display_name=_ORTHOLOGS.display_name,
                    record_type="transcript",
                )
            ],
        )
    )
    return state


async def _bind(state: AgentToolState, text: str, syntenic: str | None) -> None:
    params: Proposals = {"organism": [_NEOSPORA], "isSyntenic": syntenic}
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_to_neospora",
        text=text,
        search_name=_TRANSFORM,
        role="transform",
        params=params,
        why=SearchChoice(
            basis="organism",
            term=_NEOSPORA,
            reason=f"Transform by Orthology maps the genes into {_NEOSPORA}",
        ),
    )


@pytest.mark.asyncio
async def test_orthologs_bind_the_transform_at_the_site_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    await _bind(state, f"Carry these to their orthologs in {_NEOSPORA}", None)

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == _TRANSFORM
    assert criterion.resolved_params["isSyntenic"] == SinglePickValue(value="no")
    assert "isSyntenic" in criterion.defaulted_params
    assert criterion.resolved_params["organism"] == MultiPickValue(values=[_NEOSPORA])
    assert criterion.unexpressed_qualifiers == []


@pytest.mark.asyncio
async def test_syntenic_orthologs_still_hold_the_synteny_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await _bind(
            state, f"Carry these to their syntenic orthologs in {_NEOSPORA}", None
        )

    assert str(exc.value) == (
        "c_to_neospora states 'syntenic', and Transform by Orthology states it "
        "only through Syntenic Orthologs Only? (isSyntenic), which this call "
        "leaves at its default or switched off. Set isSyntenic to yes. Nothing "
        "was recorded."
    )
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_syntenic_orthologs_bind_with_synteny_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    await _bind(state, f"Carry these to their syntenic orthologs in {_NEOSPORA}", "yes")

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.resolved_params["isSyntenic"] == SinglePickValue(value="yes")
