"""A neighbouring search whose definition the site cannot answer is left out of
the qualifier comparison, and the bind names it; the bound search's own
definition failing still refuses the bind. "stage" is a qualifier the bound
search does not state, so the neighbours are read."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ToolReturn
from veupathdb.domain import SearchContext
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearch, WDKSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.recorded_searches import (
    client_search,
    serve_qualifier_reads,
    serve_recorded,
    suite_search,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import summary_of
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    no_count,
    no_validation,
    serve_params,
    serve_site_listing,
)

_TEXT = (
    "Carry these blood-stage genes to their syntenic orthologs in Plasmodium vivax P01"
)
_TRANSFORM = "GenesByOrthologs"
_BROKEN = "GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection"
_ORTHOLOGS = client_search("search_genes_by_orthologs")
_NEIGHBOURS = [
    suite_search("search_genes_by_ortholog_pattern"),
    suite_search("search_genes_by_gene_type"),
]


def _unreadable(name: str) -> ValidationError:
    """The refusal the catalog raises for a listed search the site answers 500 for."""
    return ValidationError(
        title="Search definition could not be read",
        detail=f"reading {name} failed: WDK request failed: '500 500'",
    )


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every definition as recorded, except the neighbour the site answers 500 for."""
    serve_recorded(monkeypatch, [_ORTHOLOGS, *_NEIGHBOURS])
    by_name = {search.url_segment: search for search in [_ORTHOLOGS, *_NEIGHBOURS]}

    def _read(name: str) -> WDKSearch:
        if name == _BROKEN:
            raise _unreadable(name)
        return by_name[name]

    serve_qualifier_reads(monkeypatch, _read)
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_ORTHOLOGS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _break_the_bound_search(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refused(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        raise _unreadable(ctx.search_name)

    monkeypatch.setattr(frame_spec, "fetch_search_details", _refused)


def _state() -> AgentToolState:
    """A pass whose ranked read answered the transform and three neighbours."""
    state = AgentToolState()
    hits = [
        CatalogHit(name=_TRANSFORM, display_name="Transform by Orthology"),
        CatalogHit(name=_BROKEN, display_name="Antibody array"),
        *(
            CatalogHit(name=search.url_segment, display_name=search.display_name)
            for search in _NEIGHBOURS
        ),
    ]
    state.record_catalog_read(
        CatalogRead(
            tool_call_id="call_orthology",
            tool="search_for_searches",
            record_type="transcript",
            query="syntenic orthologs Plasmodium vivax",
            hits=[hit.model_copy(update={"record_type": "transcript"}) for hit in hits],
        )
    )
    return state


async def _bind(state: AgentToolState) -> ToolReturn[SetCriterionResult]:
    return await set_criterion(
        frame_ctx(state),
        criterion_id="c_to_pviv",
        text=_TEXT,
        search_name=_TRANSFORM,
        role="transform",
        params={"organism": ["Plasmodium vivax P01"], "isSyntenic": "yes"},
        why=SearchChoice(
            basis="parameter",
            term="Syntenic Orthologs Only?",
            reason="Syntenic Orthologs Only? states synteny",
        ),
    )


@pytest.mark.asyncio
async def test_a_neighbour_the_site_cannot_read_does_not_refuse_the_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    result = await _bind(state)

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == _TRANSFORM
    assert returned(result, SetCriterionResult).unread_searches == [_BROKEN]
    assert summary_of(result).data["summary"] == (
        "c_to_pviv set to GenesByOrthologs, sets Syntenic Orthologs Only?; "
        "not compared: Antibody array"
    )


@pytest.mark.asyncio
async def test_the_bound_search_the_site_cannot_read_refuses_and_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    _break_the_bound_search(monkeypatch)
    state = _state()

    with pytest.raises(ValidationError) as exc:
        await _bind(state)

    assert (
        exc.value.detail
        == f"reading {_TRANSFORM} failed: WDK request failed: '500 500'"
    )
    assert state.operational_spec_draft.criteria == []


def test_a_bind_that_read_every_neighbour_carries_no_unread_list() -> None:
    result = SetCriterionResult(criterion_id="c_to_pviv", search_name=_TRANSFORM)

    assert "unreadSearches" not in result.model_dump(by_alias=True)
    assert SetCriterionResult(
        criterion_id="c_to_pviv", search_name=_TRANSFORM, unread_searches=[_BROKEN]
    ).model_dump(by_alias=True)["unreadSearches"] == [_BROKEN]
