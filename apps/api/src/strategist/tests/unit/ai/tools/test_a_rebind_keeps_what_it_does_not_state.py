from __future__ import annotations

import pytest
from pydantic import JsonValue
from veupathdb.domain.parameters import FilterValue, HeldValue

from strategist.ai.agents.state import AgentToolState
from strategist.tests.unit.ai.tools.test_frame_reads_a_value_by_its_parameter import (
    _SNPS,
    _VARIANTS,
    _every_null,
    _serve,
)
from strategist.tests.unit.ai.tools.test_frame_spec import bind

_PF = "Plasmodium falciparum 3D7"
_CAMBODIA: JsonValue = [{"field": "VAR_8e68b3e5", "value": ["Cambodia"]}]
_META = "variation_sample_meta"


async def _held(monkeypatch: pytest.MonkeyPatch) -> AgentToolState:
    _serve(monkeypatch, _SNPS)
    state = AgentToolState()
    await bind(
        state,
        _SNPS.url_segment,
        {**_every_null(_SNPS), "organismSinglePick": [_PF], _META: _CAMBODIA},
        text="SNPs in Cambodian isolates",
    )
    return state


def _clause_wire(state: AgentToolState) -> str:
    [criterion] = state.operational_spec_draft.criteria
    return criterion.resolved_params[_META].value.to_wire()


async def test_a_rebind_that_omits_a_held_clause_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _held(monkeypatch)
    held = _clause_wire(state)
    restated: dict[str, JsonValue] = {
        **{n: v for n, v in _every_null(_SNPS).items() if n != _META},
        "organismSinglePick": [_PF],
        "MinPercentMinorAlleles": 5,
    }

    result = await bind(
        state, _SNPS.url_segment, restated, text="SNPs in Cambodian isolates"
    )

    assert "Cambodia" in held
    assert _clause_wire(state) == held
    assert _META not in result.defaulted_params


async def test_a_rebind_that_omits_a_kept_value_keeps_its_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _held(monkeypatch)
    kept = HeldValue(
        wire='{"filters":[{"field":"VAR_8e68b3e5","value":["Cambodia"]}],"extra":1}'
    )
    spec = state.operational_spec_draft
    [criterion] = spec.criteria
    held = criterion.resolved_params[_META].model_copy(update={"value": kept})
    state.operational_spec_draft = spec.model_copy(
        update={
            "criteria": [
                criterion.model_copy(
                    update={
                        "resolved_params": {**criterion.resolved_params, _META: held}
                    }
                )
            ]
        }
    )
    restated: dict[str, JsonValue] = {
        **{n: v for n, v in _every_null(_SNPS).items() if n != _META},
        "organismSinglePick": [_PF],
    }

    result = await bind(
        state, _SNPS.url_segment, restated, text="SNPs in Cambodian isolates"
    )

    assert _clause_wire(state) == kept.wire
    assert _META not in result.defaulted_params


async def test_a_null_takes_the_default_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _held(monkeypatch)

    result = await bind(
        state,
        _SNPS.url_segment,
        {**_every_null(_SNPS), "organismSinglePick": [_PF]},
        text="SNPs in Cambodian isolates",
    )

    assert _clause_wire(state) == FilterValue().to_wire()
    assert _META in result.defaulted_params


async def test_a_rebind_to_another_search_keeps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _held(monkeypatch)
    _serve(monkeypatch, _VARIANTS)

    await bind(
        state,
        _VARIANTS.url_segment,
        {**_every_null(_VARIANTS), "organism_select_none": [_PF]},
        text="SNPs in Cambodian isolates",
    )

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.search_name == _VARIANTS.url_segment
    assert _META not in criterion.resolved_params
