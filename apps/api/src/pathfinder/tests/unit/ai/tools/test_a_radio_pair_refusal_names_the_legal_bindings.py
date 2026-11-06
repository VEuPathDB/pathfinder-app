"""A radio-pair refusal names only the bindings the vocabulary half allows."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import WDKVocabTerm
from veupathdb.wdk import WDKEnumParam, WDKParameter, WDKStringParam
from veupathdb_mcp.catalog import RADIO_OFF, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.tests.unit.ai.tools.test_frame_spec import bind, serve_search


def _ec(*entries: str) -> list[WDKParameter]:
    return [
        WDKEnumParam.model_validate(
            {
                "name": "ec_number_pattern",
                "type": "single-pick-vocabulary",
                "display_type": "typeAhead",
                "vocabulary": [WDKVocabTerm((v, v, None)) for v in entries],
                "initial_display_value": "2.7.11.1",
            }
        ),
        WDKStringParam(name="ec_wildcard", initial_display_value=RADIO_OFF),
    ]


async def _refusal(monkeypatch: pytest.MonkeyPatch, catalog: list[WDKParameter]) -> str:
    serve_search(
        monkeypatch,
        lambda _c: format_param_info_typed(catalog),
        catalog=catalog,
        properties={"radio-params": ["ec_number_pattern", "ec_wildcard"]},
    )
    with pytest.raises(ModelRetry) as info:
        await bind(
            AgentToolState(),
            "GenesByEcNumber",
            {"ec_number_pattern": None, "ec_wildcard": "*"},
            text="all enzymes",
        )
    return " ".join(str(info.value).split())


@pytest.mark.asyncio
async def test_a_vocabulary_that_offers_the_off_value_names_both_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = await _refusal(monkeypatch, _ec("2.7.11.1", "3.4.21.-", RADIO_OFF))

    assert "cannot be switched off" not in message
    assert (
        f"pass {RADIO_OFF} for ec_number_pattern to search by the ec_wildcard "
        f"value alone"
    ) in message
    assert "put the criterion in ec_number_pattern" in message
    assert "get_parameter_options(GenesByEcNumber, 'ec_number_pattern'" in message
    assert f"pass {RADIO_OFF} for ec_wildcard" in message


@pytest.mark.asyncio
async def test_a_vocabulary_without_the_off_value_keeps_the_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = await _refusal(monkeypatch, _ec("2.7.11.1", "3.4.21.-"))

    assert "the vocabulary half carries it and cannot be switched off" in message
    assert "ec_number_pattern default 2.7.11.1 would still contribute" in message
    assert "to search by the ec_wildcard value alone" not in message
