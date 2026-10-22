"""``set_criterion`` records a reading only when a question the researcher was
asked offered it on that criterion, bound to the value it offered."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.readings import AcceptedReading, ReadValues
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests.unit.ai.tools._rationale_catalog import choice
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
)

EVERY, SHARE = "PLAS=61T AND TOXO=0T", "PLAS>=55T AND TOXO=0T"
_SEARCH = "GroupsByPhyleticPattern"
_EXPRESSION = "phyletic_expression"
_SHARE_LABEL = "At least 55 of the 61 genomes (90%)"
_SHARE_CAVEAT = "Keeps groups missing from up to 6 genomes"
_TEXT = "present in all Plasmodium species, absent from Toxoplasma"


def _sheet(context: dict[str, str]) -> list[ParameterInfo]:
    del context
    return [param_info(_EXPRESSION, display_name="Expression")]


def _offered(criterion_id: str = "c_plas") -> list[ReadValues]:
    return [
        ReadValues(
            criterion_id=criterion_id,
            params={_EXPRESSION: EVERY},
            reading="Every one of the 61 genomes",
        ),
        ReadValues(
            criterion_id=criterion_id,
            params={_EXPRESSION: SHARE},
            reading=_SHARE_LABEL,
            caveat=_SHARE_CAVEAT,
        ),
    ]


def _state(offered: list[ReadValues]) -> AgentToolState:
    state = AgentToolState(offered_readings=offered)
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = [
        "Most of them is enough, a few missing genomes are fine",
        _TEXT,
    ]
    return state


async def _bind(state: AgentToolState, value: str, reading: str) -> None:
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_plas",
        text=_TEXT,
        search_name=_SEARCH,
        params={_EXPRESSION: value},
        why=choice("parameter", "Expression", "the expression states the reading"),
        reading=reading,
    )


@pytest.fixture(autouse=True)
def _phyletic_search(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Phyletic")


async def test_a_reading_no_question_offered_is_refused() -> None:
    state = _state([])

    with pytest.raises(ModelRetry, match="c_plas") as refused:
        await _bind(state, SHARE, _SHARE_LABEL)

    assert "no question the researcher was asked offered readings" in str(refused.value)
    assert state.operational_spec_draft.criteria == []


async def test_a_reading_offered_on_another_criterion_is_refused() -> None:
    with pytest.raises(ModelRetry, match="c_plas"):
        await _bind(_state(_offered("c_other")), SHARE, _SHARE_LABEL)


async def test_a_reading_no_offer_names_is_refused_with_the_offered_ones() -> None:
    with pytest.raises(ModelRetry) as refused:
        await _bind(_state(_offered()), SHARE, "Most of the genomes")

    assert _SHARE_LABEL in str(refused.value)
    assert "Every one of the 61 genomes" in str(refused.value)


async def test_a_reading_bound_to_another_value_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        await _bind(_state(_offered()), EVERY, _SHARE_LABEL)

    assert SHARE in str(refused.value)


async def test_an_offered_reading_answered_in_words_is_recorded() -> None:
    state = _state(_offered())

    await _bind(state, SHARE, _SHARE_LABEL)

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.accepted_reading == AcceptedReading(
        reading=_SHARE_LABEL, caveat=_SHARE_CAVEAT, params={_EXPRESSION: SHARE}
    )


async def test_a_bind_without_a_reading_records_none() -> None:
    state = _state(_offered())

    await _bind(state, SHARE, "")

    assert [
        (c.resolved_params[_EXPRESSION].value, c.accepted_reading)
        for c in state.operational_spec_draft.criteria
    ] == [(StringValue(value=SHARE), None)]


def _holding(value: str) -> AgentToolState:
    state = _state([])
    state.operational_spec_draft = OperationalSpec(
        criteria=[
            Criterion(
                id="c_plas",
                text=_TEXT,
                search_name=_SEARCH,
                resolved_params={
                    _EXPRESSION: BoundValue(
                        value=StringValue(value=value), source="card"
                    )
                },
                accepted_reading=_HELD,
            )
        ]
    )
    return state


_HELD = AcceptedReading(
    reading=_SHARE_LABEL,
    caveat=_SHARE_CAVEAT,
    params={_EXPRESSION: SHARE},
    stand_in=f"other:{_SHARE_LABEL}",
)


async def test_a_re_bind_at_the_reading_s_values_keeps_the_reading() -> None:
    state = _holding(SHARE)

    await _bind(state, SHARE, "")

    [criterion] = state.operational_spec_draft.criteria
    assert criterion.held_reading == _HELD


async def test_a_re_bind_at_other_values_ends_the_reading() -> None:
    state = _holding(SHARE)

    await _bind(state, EVERY, "")

    assert [
        (c.resolved_params[_EXPRESSION].value, c.accepted_reading)
        for c in state.operational_spec_draft.criteria
    ] == [(StringValue(value=EVERY), None)]
