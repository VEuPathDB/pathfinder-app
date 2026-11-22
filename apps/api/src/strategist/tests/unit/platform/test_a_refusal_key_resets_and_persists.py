from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKError

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.state import PipelineState
from strategist.ai.tools.standalone import _stated_values
from strategist.domain.refusal import KeyUse, Problems, RefusalKey
from strategist.platform.refusals import (
    TOOL_REFUSALS_PER_TURN,
    KeyedRefusalToolset,
    SpentRefusal,
)
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.platform.test_a_refusal_is_counted_per_key import (
    _agent,
    _deps,
    _returns,
)

_GENE = "PF3D7_1133400"
_KEY = RefusalKey(check="read_gene_record", criterion=f"gene_id={_GENE}")


def _script(tool: str, calls: list[dict[str, Any]]) -> FunctionModel:
    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(calls):
            return ModelResponse(parts=[ToolCallPart(tool, calls[made], f"tc_{made}")])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(_respond)


def _gene_reads(fails: list[bool]) -> FunctionToolset[AgentDeps]:
    async def read_gene_record(
        ctx: RunContext[AgentDeps], gene_id: str, organism: str | None = None
    ) -> str:
        del ctx, organism
        if fails.pop(0):
            msg = f"{gene_id} is not held by this turn."
            raise ModelRetry(msg)
        return gene_id

    return FunctionToolset([read_gene_record], max_retries=3)


async def test_a_refusal_between_successes_never_spends_its_key() -> None:
    fails = [True, False, True, False, True, False, True]
    deps = _deps()

    result = await _agent(
        _script("read_gene_record", [{"gene_id": _GENE}] * len(fails)),
        KeyedRefusalToolset(wrapped=_gene_reads(fails)),
    ).run("read", deps=deps)

    outcomes = [p.outcome for p in _returns(result.all_messages())]
    assert outcomes == ["failed", "success"] * 3 + ["failed"]
    assert deps.refusal_book.ledger.uses == (
        KeyUse(key=_KEY, used=1, by="read_gene_record"),
    )
    assert deps.refusal_book.spent == []


async def test_an_omitted_optional_target_is_refused_under_its_tool() -> None:
    async def save_gene_set(
        ctx: RunContext[AgentDeps], name: str, step_id: str | None = None
    ) -> str:
        del ctx, step_id
        msg = f"{name}: no step holds these genes."
        raise ModelRetry(msg)

    deps = _deps()

    result = await _agent(
        _script(
            "save_gene_set", [{"name": "kinases"}, {"name": "kinases", "step_id": None}]
        ),
        KeyedRefusalToolset(wrapped=FunctionToolset([save_gene_set])),
    ).run("save", deps=deps)

    refused = _returns(result.all_messages())
    assert [p.content for p in refused] == ["kinases: no step holds these genes."] * 2
    assert deps.refusal_book.ledger.uses == (
        KeyUse(key=RefusalKey(check="save_gene_set"), used=2, by="save_gene_set"),
    )


async def test_the_turn_ceiling_ends_every_refusal_past_it() -> None:
    fails = [True]
    deps = _deps()
    deps.refusal_book.charged = TOOL_REFUSALS_PER_TURN

    result = await _agent(
        _script("read_gene_record", [{"gene_id": _GENE}]),
        KeyedRefusalToolset(wrapped=_gene_reads(fails)),
    ).run("read", deps=deps)

    (answered,) = _returns(result.all_messages())
    assert answered.outcome == "success"
    assert SpentRefusal.model_validate(answered.content).spent[0].key == _KEY
    assert deps.refusal_book.ledger.uses == ()


async def test_a_server_error_reading_stated_values_is_not_a_refusal() -> None:
    async def _down() -> None:
        msg = "the site answered with an error"
        raise WDKError(msg, status=502)

    with pytest.raises(WDKError):
        await _stated_values._retrying("GenesByText", "written", _down())


async def test_a_client_error_reading_stated_values_is_a_refusal() -> None:
    async def _refused() -> None:
        msg = "organism has no entry 'Pf'"
        raise WDKError(msg, status=422)

    with pytest.raises(ModelRetry, match="Nothing was written"):
        await _stated_values._retrying("GenesByText", "written", _refused())


def test_a_parked_turn_resumes_with_its_refusal_book() -> None:
    state = pipeline_state(user_prompt="bind it")
    book = lead_deps(state).refusal_book
    charge = book.ledger.charge(
        Problems.one(_KEY, "not held."), 3, by="read_gene_record"
    )
    book.ledger = charge.ledger
    book.spent.append(SpentRefusal(spent=Problems.one(_KEY, "not held.").found))
    book.charged = 1

    resumed = PipelineState.model_validate(state.model_dump(mode="json", by_alias=True))

    assert lead_deps(resumed).refusal_book == book
    assert resumed.turn_markers.refusal_book.ledger.used(_KEY) == 1
