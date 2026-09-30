"""A bind of picks the model read from a cut vocabulary list records how many
of the matching entries it took."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import VocabLookup

from pathfinder.ai.agents.state import (
    AgentToolState,
    ParamVocabSnapshot,
    SearchOverview,
)
from pathfinder.domain.strategy.operational_spec import Measurement
from pathfinder.tests._support.recorded_counts import (
    PERCENTILE_SEARCH,
    recorded_count,
)
from pathfinder.tests.unit.ai.tools.test_a_bind_records_its_measurements import (
    _bound,
    _serve,
    _sheet,
)

_SAMPLES = "samples_percentile_generic"
_HIDDEN = 7


def _state_with_a_cut_read() -> AgentToolState:
    [info] = [i for i in _sheet() if i.name == _SAMPLES]
    cut = info.model_copy(
        update={
            "allowed_values_total": len(info.vocabulary()) + _HIDDEN,
            "allowed_values": info.vocabulary(),
            "vocab_lookup": VocabLookup(terms=["blood"]),
        }
    )
    state = AgentToolState()
    state.register_search(
        PERCENTILE_SEARCH,
        SearchOverview(
            search_name=PERCENTILE_SEARCH,
            display_name=PERCENTILE_SEARCH,
            record_type="transcript",
            description="",
            parameter_names=[i.name for i in _sheet()],
            required_params=[],
            param_vocab={
                _SAMPLES: ParamVocabSnapshot.model_validate(cut, from_attributes=True)
            },
        ),
    )
    return state


@pytest.mark.asyncio
async def test_a_pick_from_a_cut_list_is_measured_as_n_of_m(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, recorded_count("report_percentile_min_80"))

    criterion, _clauses = await _bound(_state_with_a_cut_read())

    picked = criterion.resolved_params[_SAMPLES].value
    assert isinstance(picked, MultiPickValue)
    assert [
        m for m in criterion.measurements if m.kind == "picked_from_a_cut_list"
    ] == [
        Measurement(
            kind="picked_from_a_cut_list",
            param=_SAMPLES,
            count=len(picked.values),
            unchosen_count=len(
                next(i for i in _sheet() if i.name == _SAMPLES).vocabulary()
            )
            + _HIDDEN
            - len(picked.values),
            reading="'blood'",
        )
    ]
