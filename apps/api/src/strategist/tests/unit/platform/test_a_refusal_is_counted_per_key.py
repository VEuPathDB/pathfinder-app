from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from pydantic_ai.usage import RunUsage
from veupathdb.errors import ValidationError

from strategist.ai.capabilities.resilience import (
    DEFAULT_CIRCUIT_BREAK_THRESHOLD,
    ToolResilience,
)
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.ai.lead.lead_agent import build_lead_toolset
from strategist.ai.tools.toolsets import eda
from strategist.ai.tools.toolsets._refusals import RefusalMemoryToolset
from strategist.domain.refusal import (
    KeyUse,
    Problem,
    Problems,
    RefusalKey,
    RefusalLedger,
)
from strategist.platform.errors import AppError, ErrorCode, UnauthorizedError
from strategist.platform.refusals import (
    TOOL_REFUSALS_PER_KEY,
    KeyedRefusalToolset,
    ProblemsRefusal,
    SpentRefusal,
    agent_capabilities,
    call_key,
    closing_of,
    last_answer,
    library_problems,
    problems_of_retry,
    refusal_text,
)
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_S = "GenesByTaxon"
C1 = RefusalKey(check="unknown_names", criterion="c1", search=_S)
C2 = RefusalKey(check="unknown_names", criterion="c2", search=_S)


@dataclass
class _Body:
    raises: Callable[[str], Exception | None]
    ran: int = 0
    retries_seen: list[int] = field(default_factory=list)

    def toolset(self) -> FunctionToolset[AgentDeps]:
        async def bind(
            ctx: RunContext[AgentDeps], criterion_id: str, search_name: str
        ) -> str:
            del search_name
            self.ran += 1
            self.retries_seen.append(ctx.retries.get("bind", 0))
            error = self.raises(criterion_id)
            if error is not None:
                raise error
            return "bound"

        return FunctionToolset([bind], max_retries=3)


def _calls(*criteria: str, search_name: str = _S) -> FunctionModel:
    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        made = sum(isinstance(m, ModelResponse) for m in messages)
        if made < len(criteria):
            args = {"criterion_id": criteria[made], "search_name": search_name}
            return ModelResponse(parts=[ToolCallPart("bind", args, f"tc_{made}")])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(_respond)


def _deps() -> AgentDeps:
    deps = agent_deps_for(
        lead_deps(pipeline_state(user_prompt="bind it")), call_id="call_test"
    )
    deps.db_session_factory = None
    return deps


def _agent(
    model: FunctionModel, toolset: AbstractToolset[AgentDeps]
) -> Agent[AgentDeps, str]:
    return Agent(
        model,
        deps_type=AgentDeps,
        toolsets=[toolset],
        capabilities=agent_capabilities([ToolResilience()]),
        retries=3,
    )


def _returns(messages: Sequence[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def _summaries(part: ToolReturnPart) -> list[str]:
    return [
        chunk.data["status"]
        for chunk in part.metadata or []
        if isinstance(chunk, DataChunk)
    ]


def _unknown(criterion_id: str) -> ProblemsRefusal:
    key = RefusalKey(check="unknown_names")
    return ProblemsRefusal(Problems.one(key, f"{criterion_id} names nothing."))


async def test_three_refusals_of_one_key_spend_no_tool_retry() -> None:
    body = _Body(raises=_unknown)
    deps = _deps()

    result = await _agent(
        _calls("c1", "c1", "c1", "c1"), KeyedRefusalToolset(wrapped=body.toolset())
    ).run("bind", deps=deps)

    first, second, third, fourth = _returns(result.all_messages())
    assert [p.outcome for p in (first, second, third)] == ["failed"] * 3
    assert [_summaries(p) for p in (first, second, third)] == [["corrected"]] * 3
    assert body.retries_seen == [0, 0, 0, 0]
    assert fourth.outcome == "success"
    assert SpentRefusal.model_validate(fourth.content).note.startswith(
        f"No more attempts for c1 / {_S}. The last refusal: c1 names nothing."
    )
    assert deps.refusal_book.ledger.used(C1) == TOOL_REFUSALS_PER_KEY
    assert [s.answer.spent for s in deps.refusal_book.spent] == [
        (Problem(key=C1, sentence="c1 names nothing."),)
    ]
    assert result.output == "done"


async def test_two_criteria_each_keep_their_own_budget() -> None:
    body = _Body(raises=_unknown)
    deps = _deps()

    result = await _agent(
        _calls("c1", "c2", "c1", "c2", "c1", "c2", "c1", "c2"),
        KeyedRefusalToolset(wrapped=body.toolset()),
    ).run("bind", deps=deps)

    outcomes = [p.outcome for p in _returns(result.all_messages())]
    assert outcomes == ["failed"] * 6 + ["success"] * 2
    assert deps.refusal_book.ledger.used(C1) == TOOL_REFUSALS_PER_KEY
    assert deps.refusal_book.ledger.used(C2) == TOOL_REFUSALS_PER_KEY


async def test_a_spent_key_beside_a_live_one_is_named_and_not_charged() -> None:
    def _both(criterion_id: str) -> ProblemsRefusal:
        del criterion_id
        return ProblemsRefusal(
            Problems(
                found=(
                    Problem(key=C2, sentence="c2 names nothing."),
                    Problem(key=C1, sentence="c1 names nothing."),
                )
            )
        )

    deps = _deps()
    deps.refusal_book.ledger = RefusalLedger(
        uses=(KeyUse(key=C1, used=TOOL_REFUSALS_PER_KEY),)
    )

    result = await _agent(
        _calls("c1"), KeyedRefusalToolset(wrapped=_Body(raises=_both).toolset())
    ).run("bind", deps=deps)

    (refused,) = _returns(result.all_messages())
    assert refused.outcome == "failed"
    assert refused.content == (
        "2 problems:\n"
        "1. c2 names nothing.\n"
        f"2. No more attempts for c1 / {_S}: c1 names nothing. "
        "Leave it out and report it. Nothing was recorded."
    )
    assert deps.refusal_book.ledger.used(C1) == TOOL_REFUSALS_PER_KEY
    assert deps.refusal_book.ledger.used(C2) == 1


async def test_a_plain_retry_is_charged_to_its_call() -> None:
    deps = _deps()

    await _agent(
        _calls("c3"),
        KeyedRefusalToolset(wrapped=_Body(raises=lambda _c: ModelRetry("x")).toolset()),
    ).run("bind", deps=deps)

    assert deps.refusal_book.ledger.uses == (
        KeyUse(
            key=RefusalKey(check="bind", criterion="c3", search=_S), used=1, by="bind"
        ),
    )


async def test_a_correctable_service_refusal_is_charged() -> None:
    conflict = AppError(
        code=ErrorCode.VALIDATION_ERROR, title="Conflict", status=409, detail="held"
    )
    deps = _deps()

    result = await _agent(
        _calls("c4"),
        KeyedRefusalToolset(wrapped=_Body(raises=lambda _c: conflict).toolset()),
    ).run("bind", deps=deps)

    (refused,) = _returns(result.all_messages())
    assert refused.outcome == "failed"
    assert refused.content == "VALIDATION_ERROR: Conflict: held"
    assert (
        deps.refusal_book.ledger.used(
            RefusalKey(check="bind", criterion="c4", search=_S)
        )
        == 1
    )


async def test_a_sign_in_refusal_ends_the_run_uncharged() -> None:
    deps = _deps()
    toolset = _Body(raises=lambda _c: UnauthorizedError(detail="sign in")).toolset()

    with pytest.raises(UnauthorizedError):
        await _agent(_calls("c4"), KeyedRefusalToolset(wrapped=toolset)).run(
            "bind", deps=deps
        )

    assert deps.refusal_book.ledger.uses == ()


def _down(criterion_id: str) -> Exception:
    del criterion_id
    return httpx.ConnectError("the site did not answer")


async def test_a_transient_failure_charges_no_key_and_trips_the_breaker() -> None:
    body = _Body(raises=_down)
    deps = _deps()

    result = await _agent(
        _calls(*["c5"] * (DEFAULT_CIRCUIT_BREAK_THRESHOLD + 1), search_name=""),
        KeyedRefusalToolset(wrapped=body.toolset()),
    ).run("bind", deps=deps)

    returns = _returns(result.all_messages())
    assert [p.outcome for p in returns] == ["retried", "retried", "retried", "success"]
    assert "SEARCH_UNAVAILABLE" in str(returns[-1].content)
    assert deps.refusal_book.ledger.uses == ()


async def test_three_refusals_after_a_transient_failure_precede_the_spent_answer() -> (
    None
):
    said: list[str] = []

    def _down_then_unknown(criterion_id: str) -> Exception:
        said.append(criterion_id)
        return _down(criterion_id) if len(said) == 1 else _unknown(criterion_id)

    deps = _deps()

    result = await _agent(
        _calls(*["c1"] * 5),
        KeyedRefusalToolset(wrapped=_Body(raises=_down_then_unknown).toolset()),
    ).run("bind", deps=deps)

    outcomes = [p.outcome for p in _returns(result.all_messages())]
    assert outcomes == ["retried", "failed", "failed", "failed", "success"]


async def test_a_held_resend_is_free_and_the_next_keeps_its_problem_keys() -> None:
    body = _Body(raises=_unknown)
    deps = _deps()

    result = await _agent(
        _calls("c1", "c1", "c1"),
        KeyedRefusalToolset(wrapped=RefusalMemoryToolset(wrapped=body.toolset())),
    ).run("bind", deps=deps)

    assert body.ran == 1
    assert [p.outcome for p in _returns(result.all_messages())] == ["failed"] * 3
    assert deps.refusal_book.ledger.uses == (KeyUse(key=C1, used=2, by="bind"),)


def test_a_refusal_reads_as_its_problems() -> None:
    problems = Problems.one(C1, "a").plus(Problems.one(C2, "b"))
    assert str(ProblemsRefusal(problems)) == (
        "2 problems:\n1. a\n2. b Nothing was recorded."
    )
    assert ProblemsRefusal(problems).problems == problems


def test_a_refusal_closes_with_the_sentence_it_was_built_with() -> None:
    read = ProblemsRefusal(Problems.one(C1, "a"), "Nothing was read.")
    assert [closing_of(read), closing_of(ModelRetry("plain"))] == [
        "Nothing was read.",
        None,
    ]
    assert str(read) == "a Nothing was read."


def test_a_refusal_names_at_least_one_problem() -> None:
    with pytest.raises(ValueError, match="at least one problem"):
        ProblemsRefusal(Problems())


def test_a_refusal_raised_in_a_call_is_placed_under_its_call() -> None:
    key = RefusalKey(check="bind", criterion="c9", search=_S)
    retry = ProblemsRefusal(Problems.one(RefusalKey(check="unknown_names"), "z"))

    assert problems_of_retry(retry, key).keys() == (
        RefusalKey(check="unknown_names", criterion="c9", search=_S),
    )
    assert problems_of_retry(ModelRetry("plain"), key) == Problems.one(key, "plain")


def _tool(*functions: Callable[..., Any]) -> dict[str, ToolDefinition]:
    return {
        name: tool.tool_def
        for name, tool in FunctionToolset(list(functions)).tools.items()
    }


def edit_step(step_id: str | None = None, reason: str = "") -> str:
    return f"{step_id}{reason}"


def test_an_absent_or_null_target_is_no_target() -> None:
    tools = _tool(edit_step)

    assert call_key(tools["edit_step"], {}) == RefusalKey(check="edit_step")
    assert call_key(tools["edit_step"], {"step_id": None}) == RefusalKey(
        check="edit_step"
    )


async def _tool_def_of(
    toolset: AbstractToolset[Any], deps: Any, name: str
) -> ToolDefinition:
    ctx: RunContext[Any] = RunContext(deps=deps, model=TestModel(), usage=RunUsage())
    return (await toolset.get_tools(ctx))[name].tool_def


async def test_the_documented_calls_without_a_target_are_keyed_by_their_tool() -> None:
    lead = await _tool_def_of(
        build_lead_toolset(), lead_deps(pipeline_state()), "save_gene_set"
    )
    step = await _tool_def_of(eda.build_toolset(), _deps(), "create_eda_step")

    assert call_key(lead, {"name": "kinases", "step_id": None}) == RefusalKey(
        check="save_gene_set"
    )
    assert call_key(step, {"criterion_id": None, "slot": "a"}) == RefusalKey(
        check="create_eda_step"
    )


def test_a_library_refusal_names_each_row() -> None:
    error = ValidationError(
        detail="two values do not read",
        errors=[
            {
                "param": "organism",
                "detail": "organism has no entry 'Pf'.",
                "value": "Pf",
            },
            {"param": "min_length", "messages": ["not a number"]},
        ],
    )
    key = RefusalKey(check="stated_value", search=_S)

    assert library_problems(error, key).found == (
        Problem(
            key=RefusalKey(check="stated_value", search=_S, parameter="organism"),
            sentence="organism has no entry 'Pf'.",
        ),
        Problem(
            key=RefusalKey(check="stated_value", search=_S, parameter="min_length"),
            sentence="two values do not read",
        ),
    )


def test_a_library_refusal_without_rows_is_one_problem() -> None:
    key = RefusalKey(check="stated_value", search=_S)

    assert library_problems(ValidationError(), key) == Problems.one(
        key, "Validation failed"
    )


def test_the_refusal_text_names_live_problems_then_spent_keys() -> None:
    charge = RefusalLedger(uses=(KeyUse(key=C1, used=1),)).charge(
        Problems.one(C1, "c1 again.").plus(Problems.one(C2, "c2 bad.")), 1
    )

    assert refusal_text(charge) == (
        "2 problems:\n1. c2 bad.\n"
        f"2. No more attempts for c1 / {_S}: c1 again. Leave it out and report it."
    )


def test_a_spent_note_names_every_spent_key() -> None:
    spent = SpentRefusal(
        spent=(
            Problem(key=C1, sentence="first."),
            Problem(key=C2, sentence="second."),
        )
    )

    assert spent.note == (
        f"No more attempts for c1 / {_S}; c2 / {_S}. The last refusal: first. "
        "Leave it out and report it in your answer."
    )
    assert spent.model_dump(by_alias=True)["note"] == spent.note


@pytest.mark.parametrize(
    ("retry", "expected"), [(0, False), (2, False), (3, True), (4, True)]
)
def test_the_last_answer_is_the_one_at_the_ceiling(retry: int, expected: bool) -> None:
    ctx: RunContext[None] = RunContext(
        deps=None, model=TestModel(), usage=RunUsage(), retry=retry, max_retries=3
    )
    assert last_answer(ctx) is expected
