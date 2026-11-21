from __future__ import annotations

import pytest
from veupathdb.domain.parameters import SinglePickValue, VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_result import SetCriterionResult
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.strategy.card_answers import params_held, spec_bound_by_card
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.value_binding import bind_values
from strategist.tests._support.catalog_builders import ParamsAt
from strategist.tests._support.catalog_reads import listing
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools._rationale_catalog import choice
from strategist.tests.unit.ai.tools.test_frame_spec import (
    frame_ctx,
    param_info,
    serve_search,
)

_SEARCH = (
    "GenesByMicroarrayDirectWithConfidencelmajFriedlin_microarrayExpression_"
    "E-MEXP-1864_Beverley_Steve_LifeStages_RSRC"
)
_PNA = "pnaVsPromastigote"
_AMA = "amastigoteVsPromastigote"
_COMPARISONS = {
    _PNA: (
        "pnaVsPromastigote (microarray)",
        (
            "PNA - Metacyclic Promastigote vs. Early Log Procyclic Promastigote "
            "(microarray)"
        ),
    ),
    _AMA: (
        "amastigoteVsPromastigote (microarray)",
        "Lesion Derived Amastigote vs. Early Log Procyclic Promastigote (microarray)",
    ),
}
_REQUEST = (
    "Leishmania major Friedlin genes that are up in amastigotes compared with "
    "promastigotes."
)


def _sheet(context: dict[str, str]) -> list[ParameterInfo]:
    term, label = _COMPARISONS[context.get("profileset_generic", _PNA)]
    return [
        param_info(
            "profileset_generic",
            "single-pick-vocabulary",
            display_name="Experiment",
            is_visible=False,
            site_set=True,
            default_value=_PNA,
            allowed_values=[VocabOption(value=v, display=v) for v in (_PNA, _AMA)],
            wire_children=["samples_fc_direct_generic_page"],
        ),
        param_info(
            "samples_fc_direct_generic_page",
            "single-pick-vocabulary",
            display_name="Comparisons",
            default_value=term,
            allowed_values=[VocabOption(value=term, display=label)],
            wire_parents=["profileset_generic"],
        ),
        param_info("fold_change", display_name="Fold change", default_value="2"),
    ]


async def _bind(
    state: AgentToolState,
    params: dict[str, str | list[str] | None],
    term: str = "Experiment",
) -> SetCriterionResult:
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = [_REQUEST]
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_ama",
            text="up in amastigotes compared with promastigotes",
            search_name=_SEARCH,
            params=params,
            why=choice(
                "parameter",
                term,
                "the amastigote comparison is the request's contrast",
            ),
        ),
        SetCriterionResult,
    )


_LEFT_OUT = "profileset_generic is set by the site, so the proposal was left out"


async def _left_out_at_another_value(
    monkeypatch: pytest.MonkeyPatch, sheet: ParamsAt
) -> tuple[list[str], str]:
    serve_search(monkeypatch, sheet, url_segment=_SEARCH, display_name="Life stages")
    state = AgentToolState()

    result = await _bind(
        state,
        {
            "profileset_generic": _AMA,
            "samples_fc_direct_generic_page": _COMPARISONS[_PNA][0],
            "fold_change": "2",
        },
        term="Fold change",
    )

    [criterion] = state.operational_spec_draft.criteria
    held = criterion.resolved_params["profileset_generic"]
    return result.corrections, held.value.to_wire()


@pytest.mark.asyncio
async def test_a_hidden_parameter_proposed_at_another_value_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _left_out_at_another_value(monkeypatch, _sheet) == (
        [_LEFT_OUT],
        _PNA,
    )


@pytest.mark.asyncio
async def test_a_hidden_parameter_left_out_travels_at_the_sites_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Life stages")
    state = AgentToolState()

    await _bind(
        state,
        {"samples_fc_direct_generic_page": _COMPARISONS[_PNA][0], "fold_change": "2"},
        term="Fold change",
    )

    [criterion] = state.operational_spec_draft.criteria
    held = criterion.resolved_params["profileset_generic"]
    assert (held.source, held.value.to_wire(), held.visible) == (
        "default",
        _PNA,
        False,
    )


@pytest.mark.asyncio
async def test_a_hidden_parameter_proposed_at_its_default_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Life stages")
    state = AgentToolState()

    result = await _bind(
        state,
        {
            "profileset_generic": _PNA,
            "samples_fc_direct_generic_page": _COMPARISONS[_PNA][0],
            "fold_change": "2",
        },
        term="Fold change",
    )

    assert result.corrections == [_LEFT_OUT]


def _read_only_sheet(context: dict[str, str]) -> list[ParameterInfo]:
    return [
        info.model_copy(update={"is_visible": True, "is_read_only": True})
        if info.name == "profileset_generic"
        else info
        for info in _sheet(context)
    ]


@pytest.mark.asyncio
async def test_a_read_only_parameter_with_a_vocabulary_is_left_to_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _left_out_at_another_value(monkeypatch, _read_only_sheet) == (
        [_LEFT_OUT],
        _PNA,
    )


@pytest.mark.asyncio
async def test_the_bind_shows_no_hidden_value(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Life stages")

    result = await _bind(
        AgentToolState(),
        {"samples_fc_direct_generic_page": _COMPARISONS[_PNA][0], "fold_change": "2"},
        term="Fold change",
    )

    assert result.resolved_params == {
        "fold_change": "2",
        "samples_fc_direct_generic_page": _COMPARISONS[_PNA][0],
    }


def _held_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="up in amastigotes",
        criteria=[
            Criterion(
                id="c_ama",
                text="up in amastigotes",
                search_name=_SEARCH,
                record_class="transcript",
                resolved_params={
                    "profileset_generic": BoundValue(
                        value=SinglePickValue(value=_PNA),
                        source="default",
                        visible=False,
                    ),
                    "fold_change": BoundValue(
                        value=SinglePickValue(value="2"), source="stated"
                    ),
                },
            )
        ],
    )


def test_a_hidden_parameter_is_held_by_no_question() -> None:
    state = AgentToolState()
    state.record_site_set(_SEARCH, _sheet({}))

    assert dict(params_held(_held_spec(), state.sets_the_site)) == {
        "c_ama": {"fold_change"}
    }


def test_a_card_binds_no_hidden_parameter() -> None:
    carded = spec_bound_by_card(
        _held_spec(),
        SetValues(criterion_id="c_ama", params={"profileset_generic": _AMA}),
        option_id="o_ama",
        sheets={_SEARCH: _sheet({})},
        expressions={},
    )

    held = carded.criteria[0].resolved_params["profileset_generic"]
    assert (held.value.to_wire(), held.source) == (_PNA, "default")


def test_a_card_leaves_a_read_only_value_at_the_sites_default() -> None:
    sheet = _read_only_sheet({})
    spec = OperationalSpec(
        goal="up in amastigotes",
        criteria=[
            Criterion(
                id="c_ama",
                text="up in amastigotes",
                search_name=_SEARCH,
                record_class="transcript",
                resolved_params=bind_values(
                    {"profileset_generic": SinglePickValue(value=_PNA)},
                    "default",
                    sheet,
                ),
            )
        ],
    )

    carded = spec_bound_by_card(
        spec,
        SetValues(criterion_id="c_ama", params={"profileset_generic": _AMA}),
        option_id="o_ama",
        sheets={_SEARCH: sheet},
        expressions={},
    )

    held = carded.criteria[0].resolved_params["profileset_generic"]
    assert (held.value.to_wire(), held.source, held.visible) == (
        _PNA,
        "default",
        True,
    )
