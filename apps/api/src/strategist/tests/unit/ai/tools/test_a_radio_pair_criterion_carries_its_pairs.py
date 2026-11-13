"""A bound criterion carries the radio pairs its search declares."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import WDKVocabTerm
from veupathdb.wdk import WDKEnumParam, WDKParameter, WDKStringParam
from veupathdb_mcp.catalog import RADIO_OFF, format_param_info_typed

from strategist.ai.agents.state import AgentToolState
from strategist.domain.strategy.step_naming import criterion_title
from strategist.tests.unit.ai.tools.test_frame_spec import bind, serve_search

_EC: list[WDKParameter] = [
    WDKEnumParam.model_validate(
        {
            "name": "ec_number_pattern",
            "type": "single-pick-vocabulary",
            "display_type": "typeAhead",
            "vocabulary": [
                WDKVocabTerm((v, v, None)) for v in ("2.7.11.1", "3.4.-.-", RADIO_OFF)
            ],
            "initial_display_value": "2.7.11.1",
        }
    ),
    WDKStringParam(name="ec_wildcard", initial_display_value=RADIO_OFF),
]


async def test_every_enzyme_is_titled_by_the_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(
        monkeypatch,
        lambda _c: format_param_info_typed(_EC),
        catalog=_EC,
        properties={"radio-params": ["ec_number_pattern", "ec_wildcard"]},
        display_name="EC Number",
    )
    state = AgentToolState()

    await bind(
        state,
        "GenesByEcNumber",
        {"ec_number_pattern": RADIO_OFF, "ec_wildcard": "*"},
        text="all enzymes",
    )

    (criterion,) = state.operational_spec_draft.criteria
    assert criterion.radio_pairs == {"ec_number_pattern": "ec_wildcard"}
    assert criterion_title(criterion).name == "EC Number: *"
