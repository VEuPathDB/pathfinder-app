"""The refusal seam every agent of this deployment carries, and its assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from assistant_core.capabilities.refused_calls import CallRefused, MarkRefusedCalls
from assistant_core.platform.observability import ReasoningEffortOnSpan
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import AgentDepsT, RunContext, ToolDefinition
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset
from veupathdb.errors import VEuPathDBError
from veupathdb.model import CamelModel, computed

from strategist.domain.refusal import (
    Charge,
    Problem,
    Problems,
    RefusalKey,
    RefusalLedger,
)
from strategist.platform.declined import DeclinedRequests
from strategist.platform.durable_worker import DurableCallsRefused
from strategist.platform.errors import AppError, ProviderKeyError

TOOL_REFUSALS_PER_KEY = 3
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
    named = CallerSuppliedIds.model_validate(args).model_dump(exclude_none=True)
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
    def __init__(self, problems: Problems) -> None:
        if problems.empty:
            msg = "a refusal names at least one problem"
            raise ValueError(msg)
        self.problems = problems
        super().__init__(problems.text())


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


class _FaultRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    param: str = ""
    detail: str = ""


_FAULT_ROWS = TypeAdapter(list[_FaultRow])


def library_problems(error: VEuPathDBError[Any], key: RefusalKey) -> Problems:
    said = error.detail or error.title
    rows = _FAULT_ROWS.validate_python(error.errors or [])
    if not rows:
        return Problems.one(key, said)
    return Problems(
        found=tuple(
            Problem(
                key=key.model_copy(update={"parameter": row.param}),
                sentence=row.detail or said,
            )
            for row in rows
        )
    )


class _CallKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    criterion_id: str = ""
    search_name: str = ""
    step_id: str = ""
    label: str = ""


def call_key(tool_name: str, args: Mapping[str, Any]) -> RefusalKey:
    named = _CallKey.model_validate(args)
    return RefusalKey(
        check=tool_name,
        criterion=named.criterion_id or named.step_id or named.label,
        search=named.search_name,
    )


@dataclass
class RefusalBook:
    ledger: RefusalLedger = field(default_factory=RefusalLedger)
    spent: list[SpentRefusal] = field(default_factory=list)


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
    name: str, args: dict[str, Any], error: ModelRetry | AppError
) -> Problems:
    key = call_key(name, args)
    match error:
        case ModelRetry():
            return problems_of_retry(error, key)
        case AppError() if the_model_can_correct(error):
            return Problems.one(key, refusal_retry_message(args, error))
        case _:
            raise error


@dataclass
class KeyedRefusalToolset[DepsT: KeepsRefusals](WrapperToolset[DepsT]):
    @property
    def id(self) -> str | None:
        return None

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[DepsT],
        tool: ToolsetTool[DepsT],
    ) -> Any:
        try:
            return await self.wrapped.call_tool(name, tool_args, ctx, tool)
        except (ModelRetry, AppError) as error:
            problems = _refused_problems(name, tool_args, error)
            book = ctx.deps.refusal_book
            charge = book.ledger.charge(problems, TOOL_REFUSALS_PER_KEY)
            book.ledger = charge.ledger
            if not charge.refused.empty:
                raise CallRefused(refusal_text(charge)) from error
            spent = SpentRefusal(spent=charge.spent.found)
            book.spent.append(spent)
            return spent


def agent_capabilities(
    carried: Sequence[AgentCapability[AgentDepsT]],
) -> list[AgentCapability[AgentDepsT]]:
    """What one agent runs with, plus the seams every agent here carries.

    A refusal this application names answers the model on every assistant, so
    an agent that declares nothing else still answers one. A durable call is
    answered the same way where no worker consumes its job. A call a tool
    refuses as sent reads as corrected, never as a failure.
    """
    return [
        ServiceRefusalRetry[AgentDepsT](),
        DeclinedRequests[AgentDepsT](),
        DurableCallsRefused[AgentDepsT](),
        ReasoningEffortOnSpan(),
        MarkRefusedCalls[AgentDepsT](),
        *carried,
    ]


__all__ = [
    "ANSWER_REFUSALS_PER_KEY",
    "LISTS_THE_IDS",
    "TOOL_REFUSALS_PER_KEY",
    "TURN_REFUSALS_PER_RULE",
    "CallerSuppliedIds",
    "KeepsRefusals",
    "KeyedRefusalToolset",
    "ProblemsRefusal",
    "RefusalBook",
    "ServiceRefusalRetry",
    "SpentRefusal",
    "agent_capabilities",
    "call_key",
    "last_answer",
    "library_problems",
    "problems_of_retry",
    "refusal_retry_message",
    "refusal_text",
    "the_model_can_correct",
]
