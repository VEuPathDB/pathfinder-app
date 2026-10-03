"""A value an answered card bound is the card's when FRAME binds the criterion
again, and an open slot keeps the kind and the display name its sheet gives."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_count, frame_spec
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
)
from pathfinder.tests._support.recorded_counts import (
    PERCENTILE_SEARCH,
    no_measurements,
)
from pathfinder.tests._support.recorded_searches import serve_recorded, suite_search
from pathfinder.tests.unit.ai.tools._rationale_catalog import SITE
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_FLOOR = "min_expression_percentile"
_SAMPLES = "samples_percentile_generic"
_REQUEST = "Also require that they are expressed in trophozoites."


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded(monkeypatch, [_PERCENTILE])
    sheet = format_param_info_typed(list(_PERCENTILE.parameters or []))

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[ParameterInfo]:
            return sheet

        return fetch_at

    async def _count(*_args: object, **_kwargs: object) -> int | None:
        return 17

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_count, "count_bound_criterion", _count)
    no_validation(monkeypatch)
    no_measurements(monkeypatch)
    serve_site_listing(monkeypatch, SITE)
    serve_no_other_sites(monkeypatch)


def _params(**values: str | list[str] | None) -> dict[str, str | list[str] | None]:
    return {
        "profileset_generic": None,
        _SAMPLES: ["asexual blood stages"],
        _FLOOR: None,
        "max_expression_percentile": None,
        "any_or_all": "all",
        "protein_coding_only": None,
    } | values


async def _bound(state: AgentToolState, **values: str | list[str] | None) -> Criterion:
    state.request_messages = [_REQUEST]
    await bind(
        state,
        PERCENTILE_SEARCH,
        _params(**values),
        criterion_id="c_troph",
        text=_REQUEST,
    )
    return next(c for c in state.operational_spec_draft.criteria if c.id == "c_troph")


@pytest.mark.asyncio
async def test_a_floor_the_card_bound_stays_the_cards_on_the_rebind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()
    held = await _bound(state)
    state.operational_spec_draft.criteria = [
        held.model_copy(
            update={
                "resolved_params": held.resolved_params
                | {
                    _FLOOR: BoundValue(
                        value=StringValue(value="1"), source="card", basis="1"
                    )
                }
            }
        )
    ]

    rebound = await _bound(state, min_expression_percentile="1")

    floor = rebound.resolved_params[_FLOOR]
    assert (floor.value, floor.source, floor.basis) == (
        StringValue(value="1"),
        "card",
        "1",
    )


@pytest.mark.asyncio
async def test_the_same_floor_with_no_card_behind_it_is_the_models_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    bound = await _bound(AgentToolState(), min_expression_percentile="1")

    assert bound.resolved_params[_FLOOR].source == "chosen"


@pytest.mark.asyncio
async def test_an_open_slot_carries_the_kind_and_the_name_its_sheet_gives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    bound = await _bound(AgentToolState(), samples_percentile_generic=None)

    assert [(s.param_name, s.param_kind) for s in bound.open_params] == [
        (_SAMPLES, "multi-pick-vocabulary")
    ]
    assert bound.param_display_names[_SAMPLES] == "Samples"
