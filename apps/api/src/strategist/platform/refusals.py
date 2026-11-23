"""The refusal seam every agent of this deployment carries, and its assembly."""

from __future__ import annotations

from collections.abc import AsyncIterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from assistant_core.capabilities.refused_calls import CallRefused, MarkRefusedCalls
from assistant_core.graph.tool_summary import summary_chunks
from assistant_core.platform.observability import ReasoningEffortOnSpan
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.exceptions import ModelRetry, ToolFailed
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolResultEvent,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition
from pydantic_ai.toolsets import AgentToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.combined import CombinedToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_core import to_jsonable_python
from veupathdb.model import CamelModel, computed

from strategist.domain.refusal import (
    Charge,
    Closing,
    Problem,
    Problems,
    RefusalKey,
    RefusalLedger,
)
from strategist.platform.declined import DeclinedRequests
from strategist.platform.durable_worker import DurableCallsRefused
from strategist.platform.errors import AppError, ProviderKeyError
from strategist.platform.refusal_keys import (
    argument_problems,
    call_key,
    sent_arguments,
)

TOOL_REFUSALS_PER_KEY = 3
TOOL_REFUSALS_PER_TURN = 20
ANSWER_REFUSALS_PER_KEY = 2
TURN_REFUSALS_PER_RULE = 1

_NOT_FOUND_STATUS = 404
_SERVER_ERROR_STATUS = 500
# An account the request does not have is not an argument the model can change.
_IDENTITY_STATUSES = frozenset({401, 403})

# The tool that lists the ids each caller-supplied argument can hold.
LISTS_THE_IDS: Mapping[str, str] = {
    "control_set_id": "list_control_sets",
    "gene_set_id": "list_gene_sets",
}


class CallerSuppliedIds(BaseModel):
    """The ids a caller chose, as one tool call carries them."""

    model_config = ConfigDict(extra="ignore")

    control_set_id: str | None = None
    gene_set_id: str | None = None


def _unknown_id_guidance(args: dict[str, Any], stated: str) -> str:
    """The listing tool for each id the refusal names, and for no other id."""
    named = CallerSuppliedIds.model_validate(to_jsonable_python(args)).model_dump(
        exclude_none=True
    )
    return " ".join(
        f"{argument}={value!r} names nothing this account holds; "
        f"call {LISTS_THE_IDS[argument]} for the ids that exist."
        for argument, value in named.items()
        if value in stated
    )


def the_model_can_correct(error: AppError) -> bool:
    """Whether another call with other arguments can pass this refusal.

    No argument pays for a model that no key may pay for.
    """
    return (
        error.status < _SERVER_ERROR_STATUS
        and error.status not in _IDENTITY_STATUSES
        and not isinstance(error, ProviderKeyError)
    )


def refusal_retry_message(args: dict[str, Any], error: AppError) -> str:
    """What the model reads in place of the call that was refused."""
    stated = f"{error.code}: {error}"
    if error.status != _NOT_FOUND_STATUS:
        return stated
    guidance = _unknown_id_guidance(args, stated)
    return f"{stated} {guidance}" if guidance else stated


@dataclass
class ServiceRefusalRetry(AbstractCapability[AgentDepsT]):
    """Turn a correctable refusal raised inside a tool body into a retry.

    A refusal this application names, below 500 and not an identity refusal, is
    a call other arguments can pass, so the model answers it. Everything else
    propagates: an invariant failure, an outage and a sign-in all end the run
    where the error path reports them.
    """

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        del ctx, call, tool_def
        if not isinstance(error, AppError) or not the_model_can_correct(error):
            raise error
        raise ModelRetry(refusal_retry_message(args, error)) from error


class ProblemsRefusal(ModelRetry):
    def __init__(
        self, problems: Problems, closing: Closing = "Nothing was recorded."
    ) -> None:
        if problems.empty:
            msg = "a refusal names at least one problem"
            raise ValueError(msg)
        self.problems = problems
        self.closing: Closing = closing
        super().__init__(f"{problems.text()} {closing}")


def closing_of(error: BaseException) -> Closing | None:
    match error:
        case ProblemsRefusal(closing=closing):
            return closing
        case _:
            return None


def refuse_problems(problems: Problems) -> None:
    if not problems.empty:
        raise ProblemsRefusal(problems)


class SpentRefusal(CamelModel):
    model_config = ConfigDict(frozen=True)

    spent: tuple[Problem, ...]

    @computed
    def note(self) -> str:
        labels = "; ".join(
            key.label() for key in dict.fromkeys(p.key for p in self.spent)
        )
        return (
            f"No more attempts for {labels}. The last refusal: "
            f"{self.spent[0].sentence} Leave it out and report it in your answer."
        )


def problems_of_retry(retry: ModelRetry, key: RefusalKey) -> Problems:
    match retry:
        case ProblemsRefusal(problems=problems):
            return problems.under(criterion=key.criterion, search=key.search)
        case _:
            return Problems.one(key, retry.message)


class CallSpent(ToolFailed):
    pass


class SpentCall(CamelModel):
    model_config = ConfigDict(frozen=True)

    answer: SpentRefusal
    by: str
    run_id: str = ""

    def without(self, on: RefusalKey) -> SpentCall | None:
        kept = tuple(p for p in self.answer.spent if not on.clears(p.key, by=self.by))
        if not kept:
            return None
        return self.model_copy(update={"answer": SpentRefusal(spent=kept)})


class RefusalBook(CamelModel):
    ledger: RefusalLedger = Field(default_factory=RefusalLedger)
    spent: list[SpentCall] = Field(default_factory=list)
    charged: int = 0

    def spend(self, spent: Problems, *, by: str, run_id: str) -> SpentRefusal:
        answer = SpentRefusal(spent=spent.found)
        self.spent.append(SpentCall(answer=answer, by=by, run_id=run_id))
        return answer

    def clear(self, on: RefusalKey) -> None:
        self.ledger = self.ledger.cleared(on)
        self.spent = [
            kept for call in self.spent if (kept := call.without(on)) is not None
        ]

    def spent_in(self, run_id: str) -> list[SpentRefusal]:
        firsts: dict[RefusalKey, Problem] = {}
        for call in self.spent:
            if call.run_id == run_id:
                for problem in call.answer.spent:
                    firsts.setdefault(problem.key, problem)
        return [SpentRefusal(spent=(problem,)) for problem in firsts.values()]


class KeepsRefusals(Protocol):
    @property
    def refusal_book(self) -> RefusalBook: ...


def _first_sentences(problems: Problems) -> dict[RefusalKey, str]:
    firsts: dict[RefusalKey, str] = {}
    for problem in problems.found:
        firsts.setdefault(problem.key, problem.sentence)
    return firsts


def refusal_text(charge: Charge) -> str:
    lines = [p.sentence for p in charge.refused.found] + [
        f"No more attempts for {key.label()}: {sentence} Leave it out and report it."
        for key, sentence in _first_sentences(charge.spent).items()
    ]
    if len(lines) == 1:
        return lines[0]
    numbered = [f"{i}. {line}" for i, line in enumerate(lines, start=1)]
    return "\n".join([f"{len(lines)} problems:", *numbered])


def last_answer(ctx: RunContext[Any]) -> bool:
    return ctx.retry >= ctx.max_retries


def _refused_problems(
    tool: ToolDefinition, args: dict[str, Any], error: ModelRetry | AppError
) -> Problems:
    key = call_key(tool, args)
    match error:
        case ModelRetry():
            return problems_of_retry(error, key)
        case AppError() if the_model_can_correct(error):
            return Problems.one(key, refusal_retry_message(args, error))
        case _:
            raise error


def answered(
    book: RefusalBook,
    problems: Problems,
    *,
    by: str,
    run_id: str,
    closing: Closing | None,
) -> CallRefused | CallSpent:
    if book.charged >= TOOL_REFUSALS_PER_TURN:
        return CallSpent(book.spend(problems, by=by, run_id=run_id).note)
    charge = book.ledger.charge(problems, TOOL_REFUSALS_PER_KEY, by=by)
    book.ledger = charge.ledger
    if charge.refused.empty:
        return CallSpent(book.spend(charge.spent, by=by, run_id=run_id).note)
    book.charged += 1
    said = refusal_text(charge)
    return CallRefused(f"{said} {closing}" if closing else said)


class _ToolMarks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keyed_refusals: bool = False


def _keyed[DepsT](tool: ToolsetTool[DepsT]) -> ToolsetTool[DepsT]:
    marked = {**(tool.tool_def.metadata or {}), "keyed_refusals": True}
    return replace(tool, tool_def=replace(tool.tool_def, metadata=marked))


@dataclass
class KeyedRefusalToolset[DepsT: KeepsRefusals](WrapperToolset[DepsT]):
    @property
    def id(self) -> str | None:
        return None

    async def get_tools(self, ctx: RunContext[DepsT]) -> dict[str, ToolsetTool[DepsT]]:
        tools = await self.wrapped.get_tools(ctx)
        return {name: _keyed(tool) for name, tool in tools.items()}

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[DepsT],
        tool: ToolsetTool[DepsT],
    ) -> Any:
        book = ctx.deps.refusal_book
        try:
            result = await self.wrapped.call_tool(name, tool_args, ctx, tool)
        except (ModelRetry, AppError) as error:
            raise answered(
                book,
                _refused_problems(tool.tool_def, tool_args, error),
                by=name,
                run_id=ctx.run_id or "",
                closing=closing_of(error),
            ) from error
        book.clear(call_key(tool.tool_def, tool_args))
        return result


@dataclass
class ChargedArgumentRefusals[DepsT: KeepsRefusals](AbstractCapability[DepsT]):
    refused: dict[str, str] = field(default_factory=dict)

    async def for_run(self, ctx: RunContext[DepsT]) -> ChargedArgumentRefusals[DepsT]:
        del ctx
        return ChargedArgumentRefusals[DepsT]()

    async def on_tool_validate_error(
        self,
        ctx: RunContext[DepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
        error: ValidationError | ModelRetry,
    ) -> dict[str, Any]:
        if not _ToolMarks.model_validate(tool_def.metadata or {}).keyed_refusals:
            raise error
        sent = sent_arguments(args)
        match error:
            case ValidationError():
                problems = argument_problems(tool_def, sent, error)
                closing: Closing | None = "Nothing was recorded."
            case ModelRetry():
                problems = _refused_problems(tool_def, sent, error)
                closing = closing_of(error)
        answer = answered(
            ctx.deps.refusal_book,
            problems,
            by=tool_def.name,
            run_id=ctx.run_id or "",
            closing=closing,
        )
        match answer:
            case CallRefused(message=said):
                self.refused[call.tool_call_id] = said
            case CallSpent():
                pass
        raise answer from error

    async def wrap_run_event_stream(
        self,
        ctx: RunContext[DepsT],
        *,
        stream: AsyncIterable[AgentStreamEvent],
    ) -> AsyncIterable[AgentStreamEvent]:
        del ctx
        async for event in stream:
            match event:
                case FunctionToolResultEvent(
                    part=ToolReturnPart(outcome="failed", tool_call_id=call_id) as part
                ) if call_id in self.refused:
                    said = self.refused.pop(call_id)
                    part.metadata = summary_chunks(call_id, said, status="corrected")
                case _:
                    pass
            yield event


def _holds_keyed(toolsets: Sequence[AgentToolset[Any]]) -> bool:
    return any(_is_keyed(toolset) for toolset in toolsets)


def _is_keyed(toolset: AgentToolset[Any]) -> bool:
    match toolset:
        case KeyedRefusalToolset():
            return True
        case WrapperToolset(wrapped=inner):
            return _is_keyed(inner)
        case CombinedToolset(toolsets=inner):
            return _holds_keyed(inner)
        case _:
            return False


def agent_capabilities(
    carried: Sequence[AgentCapability[AgentDepsT]],
    *,
    toolsets: Sequence[AgentToolset[AgentDepsT]],
) -> list[AgentCapability[AgentDepsT]]:
    """What one agent runs with, plus the seams every agent here carries.

    A refusal this application names answers the model on every assistant, so
    an agent that declares nothing else still answers one. A durable call is
    answered the same way where no worker consumes its job. A call a tool
    refuses as sent reads as corrected, never as a failure. An agent whose
    toolsets count refusals per key charges its shape errors to the same keys.
    """
    charged: list[AgentCapability[Any]] = (
        [ChargedArgumentRefusals[Any]()] if _holds_keyed(toolsets) else []
    )
    return [
        ServiceRefusalRetry[AgentDepsT](),
        DeclinedRequests[AgentDepsT](),
        DurableCallsRefused[AgentDepsT](),
        ReasoningEffortOnSpan(),
        MarkRefusedCalls[AgentDepsT](),
        *charged,
        *carried,
    ]


__all__ = [
    "ANSWER_REFUSALS_PER_KEY",
    "LISTS_THE_IDS",
    "TOOL_REFUSALS_PER_KEY",
    "TOOL_REFUSALS_PER_TURN",
    "TURN_REFUSALS_PER_RULE",
    "CallSpent",
    "CallerSuppliedIds",
    "ChargedArgumentRefusals",
    "KeepsRefusals",
    "KeyedRefusalToolset",
    "ProblemsRefusal",
    "RefusalBook",
    "ServiceRefusalRetry",
    "SpentCall",
    "SpentRefusal",
    "agent_capabilities",
    "answered",
    "closing_of",
    "last_answer",
    "problems_of_retry",
    "refusal_retry_message",
    "refusal_text",
    "refuse_problems",
    "the_model_can_correct",
]
