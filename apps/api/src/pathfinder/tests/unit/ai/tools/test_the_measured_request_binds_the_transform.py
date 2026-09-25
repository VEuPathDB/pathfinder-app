"""The measured request binds the search whose parameter states its qualifier.

"syntenic" is a word of the criterion that plasmodb's Transform by Orthology
states through a parameter and its Orthology Phylogenetic Profile cannot. Both
definitions and the transcript listing are the ones plasmodb published.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, CatalogHit, CatalogRead
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import CriterionRole
from pathfinder.tests._support.recorded_searches import (
    client_search,
    serve_recorded,
    suite_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    Proposals,
    frame_ctx,
    no_count,
    no_validation,
    serve_params,
    serve_site_listing,
)

_TEXT = "keep only those with syntenic orthologs in Plasmodium vivax P01"
_TRANSFORM = "GenesByOrthologs"
_PROFILE = "GenesByOrthologPattern"
_ORTHOLOGS = client_search("search_genes_by_orthologs")
_PATTERN = suite_search("search_genes_by_ortholog_pattern")


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_ORTHOLOGS, _PATTERN])
    serve_params(
        monkeypatch,
        lambda _context: format_param_info_typed(_ORTHOLOGS.parameters or []),
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    serve_site_listing(monkeypatch, [])


def _read(*names: str) -> CatalogRead:
    """The ranked answer that named these orthology searches for this criterion."""
    display = {_TRANSFORM: _ORTHOLOGS.display_name, _PROFILE: _PATTERN.display_name}
    return CatalogRead(
        tool_call_id="call_orthology",
        tool="search_for_searches",
        record_type="transcript",
        query="syntenic orthologs Plasmodium vivax",
        hits=[
            CatalogHit(name=name, display_name=display[name], record_type="transcript")
            for name in names or (_PROFILE, _TRANSFORM)
        ],
    )


def _state(*names: str) -> AgentToolState:
    state = AgentToolState()
    state.record_catalog_read(_read(*names))
    return state


async def _open(
    state: AgentToolState, search_name: str, role: CriterionRole, text: str = _TEXT
) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_to_pviv",
        text=text,
        search_name=search_name,
        role=role,
    )


async def _bind(state: AgentToolState, syntenic: str | None) -> None:
    params: Proposals = {
        "organism": ["Plasmodium vivax P01"],
        "isSyntenic": syntenic,
    }
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_to_pviv",
        text=_TEXT,
        search_name=_TRANSFORM,
        role="transform",
        params=params,
        why=SearchChoice(
            basis="parameter",
            term="Syntenic Orthologs Only?",
            reason=(
                "Syntenic Orthologs Only? states synteny; Orthology Phylogenetic "
                "Profile has no synteny parameter"
            ),
        ),
    )


@pytest.mark.asyncio
async def test_the_profile_is_refused_naming_the_transform_and_its_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await _open(state, _PROFILE, "filter")

    assert str(exc.value) == (
        "c_to_pviv: Orthology Phylogenetic Profile has no parameter that states "
        "'syntenic'. On plasmodb, Transform by Orthology carries 'syntenic' "
        "(Syntenic Orthologs Only?). Bind that search as a transform; to keep "
        "the source genes, state the round trip: the source INTERSECT a "
        "transform back to the source organism over a transform to the named "
        "organism over a copy of the source. Nothing was recorded."
    )
    assert state.operational_spec_draft.criteria == []
    assert state.open_sheets == {}


@pytest.mark.asyncio
async def test_the_transform_opens_its_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch)
    state = _state()

    await _open(state, _TRANSFORM, "transform")

    assert list(state.open_sheets) == ["c_to_pviv"]


@pytest.mark.parametrize("syntenic", [None, "no"])
@pytest.mark.asyncio
async def test_the_transform_without_synteny_is_refused(
    monkeypatch: pytest.MonkeyPatch, syntenic: str | None
) -> None:
    _serve(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as exc:
        await _bind(state, syntenic)

    assert str(exc.value) == (
        "c_to_pviv states 'syntenic', and Transform by Orthology states it only "
        "through Syntenic Orthologs Only? (isSyntenic), which this call leaves at "
        "its default or switched off. Set isSyntenic to yes. Nothing was recorded."
    )
    assert state.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_the_transform_with_synteny_binds_on_its_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    await _bind(state, "yes")

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == _TRANSFORM
    assert criterion.resolved_params["isSyntenic"] == SinglePickValue(value="yes")
    assert criterion.resolved_params["organism"] == MultiPickValue(
        values=["Plasmodium vivax P01"]
    )
    assert criterion.rationale is not None
    assert criterion.rationale.kind == "search"
    assert criterion.rationale.basis == "parameter"
    assert criterion.rationale.term == "Syntenic Orthologs Only?"
    assert [c.name for c in criterion.rationale.compared] == [_PROFILE]
    assert criterion.unexpressed_qualifiers == []


@pytest.mark.asyncio
async def test_non_syntenic_orthologs_open_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()

    await _open(
        state, _PROFILE, "filter", "keep those with non-syntenic orthologs in P. vivax"
    )

    assert list(state.open_sheets) == ["c_to_pviv"]


@pytest.mark.asyncio
async def test_a_transform_this_pass_never_read_refuses_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state(_PROFILE)

    await _open(state, _PROFILE, "filter")

    assert list(state.open_sheets) == ["c_to_pviv"]
