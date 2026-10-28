from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import MultiPickValue, VocabOption
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import (
    ParameterInfo,
    VocabPick,
    post_decision,
    use_decisions_transport,
)

from pathfinder.ai.agents.frame_pick_checks import hold_an_unsettled_pick_to_a_question
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone.catalog_discovery import get_parameter_options
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    ValueSource,
)
from pathfinder.domain.strategy.question_options import SetValues
from pathfinder.domain.strategy.vocab_picks import PickRead
from pathfinder.platform.config import get_settings
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    patch_search_details,
)

_FIXTURES = Path(__file__).parents[3] / "fixtures/decisions"
_SITE = _FIXTURES / "plasmodb_3d7_interpro_vocabulary_half_off.json"
_PICK = _FIXTURES / "decisions_plasmodb_interpro_pick.json"
_DECISIONS = "https://api.openai.com/v1/decisions"
_SEARCH = "GenesByInterproDomain"
_PARAM = "domain_typeahead"
_CONTEXT = {"organism": ["Plasmodium falciparum 3D7"], "domain_database": "INTERPRO"}
_REQUIREMENT = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value="protein kinase",
    label="protein kinase",
    source=ConstraintSource.USER_EXPLICIT,
)


def _exchanges() -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = json.loads(_PICK.read_text())["exchanges"]
    return exchanges


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = WDKSearchResponse.model_validate(
        json.loads(_SITE.read_text())["response_json"]
    )
    patch_search_details(monkeypatch, parameters=recorded.search_data.parameters or [])


@pytest.fixture
def decisions(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-key")
    use_decisions_transport(post_decision)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _context() -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.stated_requirements = [_REQUIREMENT]
    return ctx


async def _read(ctx: RunContext[AgentDeps]) -> ParameterInfo:
    return returned(
        await get_parameter_options(
            ctx,
            _SEARCH,
            _PARAM,
            context_values=_CONTEXT,
            query="protein kinase",
            requirement="R1",
        ),
        ParameterInfo,
    )


def _bound(ctx: RunContext[AgentDeps], value: str, source: ValueSource) -> None:
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[
            Criterion(
                id="c_kinase",
                text="protein kinase domain",
                search_name=_SEARCH,
                record_class="transcript",
                resolved_params={
                    _PARAM: BoundValue(
                        value=MultiPickValue(values=[value]),
                        source=source,
                        display_name="Specific Domain(s)",
                    )
                },
            )
        ]
    )


async def _recorded_read(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
    choice, fit = _exchanges()
    with respx.mock() as router:
        route = router.post(_DECISIONS).mock(
            side_effect=[
                httpx.Response(200, json=choice["response"]),
                httpx.Response(200, json=fit["response"]),
            ]
        )
        await _read(ctx)
    return [json.loads(call.request.content) for call in route.calls]


@pytest.mark.usefixtures("site", "decisions")
async def test_the_requirement_words_reach_the_recorded_choice_and_fit() -> None:
    sent = await _recorded_read(_context())

    assert sent == [exchange["request"] for exchange in _exchanges()]


@pytest.mark.usefixtures("site", "decisions")
async def test_a_choice_the_fit_doubts_is_asked_with_the_pick_and_kept_entries() -> (
    None
):
    ctx = _context()
    await _recorded_read(ctx)
    _bound(ctx, "IPR011009", "chosen")

    held = hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="ready"))

    assert isinstance(held, FrameResult)
    (asked,) = held.open_questions
    assert (held.disposition, asked.criterion_id, asked.param_name) == (
        "needs_user",
        "c_kinase",
        _PARAM,
    )
    assert asked.recommended_value == "IPR011009"
    assert asked.options[:3] == ["IPR011009", "IPR050205", "IPR011641"]
    assert asked.question == (
        "Which Specific Domain(s) states 'protein kinase'? On this site the "
        "nearest entry is IPR011009 : Protein kinase-like (PK-like), confidence "
        "0.31. Pick an entry, or say in your own words what you mean."
    )
    (typed,) = held.questions(ctx.deps.agent_state.operational_spec_draft)
    assert typed.options[0].label == "IPR011009 : Protein kinase-like (PK-like)"
    assert typed.options[0].binding == SetValues(
        criterion_id="c_kinase", params={_PARAM: "IPR011009"}
    )


@pytest.mark.usefixtures("site", "decisions")
async def test_the_read_tells_frame_the_pick_does_not_settle_it() -> None:
    ctx = _context()
    choice, fit = _exchanges()
    with respx.mock() as router:
        router.post(_DECISIONS).mock(
            side_effect=[
                httpx.Response(200, json=choice["response"]),
                httpx.Response(200, json=fit["response"]),
            ]
        )
        read = await _read(ctx)

    assert read.note is not None
    assert read.note.endswith(
        "The nearest entry to 'protein kinase' is IPR011009 (IPR011009 : Protein "
        "kinase-like (PK-like)), confidence 0.31, which does not settle it, so a "
        "binding of this parameter is asked of the researcher."
    )


@pytest.mark.usefixtures("site", "decisions")
async def test_a_value_the_researcher_stated_is_not_asked() -> None:
    ctx = _context()
    await _recorded_read(ctx)
    _bound(ctx, "IPR011009", "stated")

    held = hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="ready"))

    assert held == FrameResult(summary="ready")


@pytest.mark.usefixtures("site")
async def test_when_the_service_does_not_answer_the_pass_is_unchanged() -> None:
    ctx = _context()
    read = await _read(ctx)
    _bound(ctx, "IPR011009", "chosen")

    held = hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="ready"))

    assert (read.vocab_pick, ctx.deps.agent_state.vocab_picks) == (None, {})
    assert held == FrameResult(summary="ready")


def test_a_settled_pick_is_told_as_the_entry_to_bind_and_never_asked() -> None:
    ctx = _context()
    settled = PickRead(
        search_name=_SEARCH,
        param_name=_PARAM,
        requirement="protein kinase",
        pick=VocabPick(
            value="IPR000719",
            display="IPR000719 : Protein kinase domain",
            choice_confidence=0.91,
            fit_probability=0.88,
            min_confidence=0.5,
            offered=2,
        ),
        kept=[
            VocabOption(value="IPR000719", display="IPR000719 : Protein kinase domain")
        ],
    )
    ctx.deps.agent_state.record_pick(settled)
    _bound(ctx, "IPR000719", "chosen")

    held = hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="ready"))

    assert settled.note() == (
        "The entry that states 'protein kinase' is IPR000719 (IPR000719 : Protein "
        "kinase domain), confidence 0.88: bind it unless the request names "
        "another entry."
    )
    assert held == FrameResult(summary="ready")


@pytest.mark.usefixtures("site")
async def test_a_requirement_the_list_does_not_number_is_refused() -> None:
    ctx = _context()

    with pytest.raises(ModelRetry, match="holds R1"):
        await get_parameter_options(
            ctx, _SEARCH, _PARAM, context_values=_CONTEXT, requirement="R7"
        )
