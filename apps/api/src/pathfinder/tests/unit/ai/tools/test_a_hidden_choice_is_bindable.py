"""A hidden parameter with a vocabulary is a choice the bind takes; only a
hidden parameter without one is the site's to set. The choice is a term a
reason names and a row the researcher audits.

The sheet is the tritrypdb life-stage comparison as WDK publishes it:
``profileset_generic`` is hidden, not read-only, with two comparisons, and
the visible comparison list depends on it.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._rationale_catalog import choice
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
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
            default_value=_PNA,
            allowed_values=[VocabOption(value=v, display=v) for v in (_PNA, _AMA)],
            controls_vocab_of=["samples_fc_direct_generic_page"],
        ),
        param_info(
            "samples_fc_direct_generic_page",
            "single-pick-vocabulary",
            display_name="Comparisons",
            default_value=term,
            allowed_values=[VocabOption(value=term, display=label)],
            vocab_depends_on=["profileset_generic"],
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


@pytest.mark.asyncio
async def test_a_hidden_parameter_with_a_vocabulary_takes_another_of_its_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Life stages")
    state = AgentToolState()

    result = await _bind(
        state,
        {
            "profileset_generic": _AMA,
            "samples_fc_direct_generic_page": _COMPARISONS[_AMA][0],
            "fold_change": "2",
        },
    )

    [criterion] = state.operational_spec_draft.criteria
    bound = criterion.resolved_params["profileset_generic"]
    assert (result.corrections, bound.source, result.resolved_params) == (
        [],
        "chosen",
        {
            "profileset_generic": _AMA,
            "samples_fc_direct_generic_page": _COMPARISONS[_AMA][0],
            "fold_change": "2",
        },
    )


@pytest.mark.asyncio
async def test_a_hidden_choice_left_out_is_the_sites_default(
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
    bound = criterion.resolved_params["profileset_generic"]
    assert (bound.source, bound.value.to_wire()) == ("default", _PNA)


@pytest.mark.asyncio
async def test_a_hidden_choice_is_a_visible_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _sheet, url_segment=_SEARCH, display_name="Life stages")
    state = AgentToolState()

    await _bind(
        state,
        {
            "profileset_generic": _AMA,
            "samples_fc_direct_generic_page": _COMPARISONS[_AMA][0],
            "fold_change": "2",
        },
    )

    [criterion] = state.operational_spec_draft.criteria
    assert (
        criterion.resolved_params["profileset_generic"].visible,
        criterion.rationale is not None and criterion.rationale.term,
    ) == (True, "Experiment")


def _read_only_sheet(context: dict[str, str]) -> list[ParameterInfo]:
    """The life-stage sheet with the Experiment marked read-only by the site."""
    return [
        info.model_copy(update={"is_read_only": True})
        if info.name == "profileset_generic"
        else info
        for info in _sheet(context)
    ]


@pytest.mark.asyncio
async def test_a_read_only_parameter_with_a_vocabulary_is_left_to_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(
        monkeypatch, _read_only_sheet, url_segment=_SEARCH, display_name="Life stages"
    )
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await _bind(
            state,
            {
                "profileset_generic": _AMA,
                "samples_fc_direct_generic_page": _COMPARISONS[_AMA][0],
                "fold_change": "2",
            },
        )

    assert str(refused.value) == (
        f"profileset_generic on {_SEARCH} is set by the site to '{_PNA}' and takes "
        "no other value; leave it out of params. The names params takes: "
        "['fold_change', 'samples_fc_direct_generic_page']."
    )
