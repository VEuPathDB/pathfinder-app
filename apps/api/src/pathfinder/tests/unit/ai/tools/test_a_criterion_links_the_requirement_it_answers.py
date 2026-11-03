from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_answers import AnsweredRequirement
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, RequirementLink
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    default_why,
    frame_ctx,
    param_info,
    serve_resolution,
    serve_search,
)

_ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium falciparum 3D7",
    label="organism",
    source=ConstraintSource.USER_EXPLICIT,
)
_SIGNAL = Constraint(
    kind=ConstraintKind.PROPERTY,
    requested_value="a signal peptide",
    label="signal peptide",
    source=ConstraintSource.USER_EXPLICIT,
)
_SEARCH = "GenesWithSignalPeptide"


def _state() -> AgentToolState:
    state = AgentToolState()
    state.stated_requirements = [_ORGANISM, _SIGNAL]
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = ["signal peptide genes of P. falciparum 3D7"]
    return state


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = {"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])}
    serve_search(
        monkeypatch, lambda _context: [param_info("organism", "multi-pick-vocabulary")]
    )
    serve_resolution(monkeypatch, bound)

    async def _validate(_ctx: object, **_kw: object) -> ValidatedParams:
        return ValidatedParams(params=dict(bound))

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)


async def _bind(
    state: AgentToolState, answers: list[AnsweredRequirement] | None
) -> list[RequirementLink]:
    params: dict[str, str | list[str] | None] = {"organism": None}
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_signal",
        text="genes with a signal peptide",
        search_name=_SEARCH,
        params=params,
        why=default_why(_SEARCH, params),
        answers=answers,
    )
    [criterion] = state.operational_spec_draft.criteria
    return criterion.answers


@pytest.mark.asyncio
async def test_a_bound_criterion_links_each_number_to_the_held_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    links = await _bind(
        _state(),
        [
            AnsweredRequirement(requirement="R1", param="organism"),
            AnsweredRequirement(requirement="R2"),
        ],
    )

    assert links == [
        RequirementLink(requirement=_ORGANISM.id, param="organism"),
        RequirementLink(requirement=_SIGNAL.id),
    ]


@pytest.mark.asyncio
async def test_a_link_to_the_result_size_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    links = await _bind(
        _state(), [AnsweredRequirement(requirement="R2", result_size=True)]
    )

    assert links == [RequirementLink(requirement=_SIGNAL.id, result_size=True)]


def test_a_result_size_with_a_parameter_is_sent_back() -> None:
    with pytest.raises(ValueError, match="null param"):
        AnsweredRequirement(requirement="R2", param="organism", result_size=True)


@pytest.mark.asyncio
async def test_a_number_the_list_lacks_is_sent_back_with_the_numbers_it_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry, match=r"\['R3'\].*holds R1, R2"):
        await _bind(_state(), [AnsweredRequirement(requirement="R3")])


@pytest.mark.asyncio
async def test_a_param_the_sheet_lacks_is_sent_back_with_the_sheet_s_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry, match=r"\['fold_change'\].*\['organism'\]"):
        await _bind(
            _state(), [AnsweredRequirement(requirement="R2", param="fold_change")]
        )


@pytest.mark.asyncio
async def test_a_rebind_that_names_no_answers_keeps_the_held_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()
    held = [RequirementLink(requirement=_SIGNAL.id)]
    state.frame_set_criterion(
        Criterion(id="c_signal", text="signal peptide", answers=held)
    )

    assert await _bind(state, None) == held


@pytest.mark.asyncio
async def test_an_empty_list_says_the_criterion_answers_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = _state()
    state.frame_set_criterion(
        Criterion(
            id="c_signal",
            text="signal peptide",
            answers=[RequirementLink(requirement=_SIGNAL.id)],
        )
    )

    assert await _bind(state, []) == []
