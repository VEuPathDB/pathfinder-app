"""The wrong call of each fault, made from the call the arc was about to make."""

from __future__ import annotations

import re
from collections.abc import Callable

from assistant_core.models.scripted import (
    called_tool_parts,
    scripted_call,
    tool_return_parts,
)
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import history_free
from pathfinder.ai.models.mock.history import head_work_order
from pathfinder.ai.models.mock.message_words import turn_controls
from pathfinder.ai.models.mock.reads import instructions_of
from pathfinder.ai.models.mock.sheets import workspace_criteria
from pathfinder.ai.models.mock.specs import criterion_replies
from pathfinder.domain.evidence import VerificationReview

CRITERION = "set_criterion"
CONTROL_TEST = "run_control_tests_on_step"
SWEEP = "optimize_search_parameters"
CONSULT = "consult_user"
ANSWER = "final_result"
DELETE = "delete_step"

UNLISTED_SEARCH = "GenesByNoSuchSearch"
UNLISTED_ORGANISM = "Organismus fictus"
SHORT_REPLY = "[mock] Two"
# The step the delete card's removal leaves standing.
MISNAMED_DELETION = "Removed the signal peptide step."
# A reason over the 160-character cap that names no parameter.
LONG_REASON = (
    "Chosen because the catalog ranked it first for this part of the request, "
    "and because its settings cover what the researcher described in the message "
    "about these genes and their predicted features."
)
# The line the order of a pass that continues a stopped pass carries.
_CONTINUATION = "are bound already and stay exactly as they are"
_STRATEGY_COUNT = re.compile(r"(?P<count>\d[\d,]*) genes\b")

# The wrong call made in place of the call the arc was about to make, or None.
CallFault = Callable[[ToolCallPart], ToolCallPart | None]
# What a fault reads of the run, and the call fault it answers with.
WrongCall = Callable[[list[ModelMessage]], CallFault]


class _Why(BaseModel):
    model_config = ConfigDict(extra="allow")

    term: str
    reason: str = ""


class _Binding(BaseModel):
    """A ``set_criterion`` call's arguments, the keys the arc sent and no others."""

    model_config = ConfigDict(extra="allow")

    search_name: str = ""
    params: dict[str, str | list[str] | None] | None = None
    why: _Why | None = None

    def args(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)


def _binding(intended: ToolCallPart) -> _Binding | None:
    """The arc's binding call, or None when it is another call or a sheet read."""
    if intended.tool_name != CRITERION:
        return None
    found = _Binding.model_validate(intended.args_as_dict())
    return found if found.params is not None else None


def _criterion(binding: _Binding) -> ToolCallPart:
    return scripted_call(CRITERION, binding.args())


def _unlisted_search(intended: ToolCallPart) -> ToolCallPart | None:
    """The sheet read of the arc's criterion, on a search the listing never named."""
    if intended.tool_name != CRITERION or _binding(intended) is not None:
        return None
    return scripted_call(
        CRITERION, {**intended.args_as_dict(), "search_name": UNLISTED_SEARCH}
    )


def _value_as_term(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's binding with the value it sets passed as the parameter term."""
    binding = _binding(intended)
    if binding is None or binding.why is None or binding.params is None:
        return None
    match binding.params.get(binding.why.term):
        case [str() as value, *_] | (str() as value):
            why = binding.why.model_copy(update={"term": value})
            return _criterion(binding.model_copy(update={"why": why}))
        case _:
            return None


def _off_vocabulary(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's binding with its organism replaced by one no vocabulary lists."""
    binding = _binding(intended)
    if binding is None or binding.params is None or "organism" not in binding.params:
        return None
    params = {**binding.params, "organism": [UNLISTED_ORGANISM]}
    return _criterion(binding.model_copy(update={"params": params}))


def _syntenic_left_off(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's syntenic binding with its synteny parameter left at the default."""
    binding = _binding(intended)
    if binding is None or binding.params is None:
        return None
    synteny = [name for name in binding.params if "synten" in name.casefold()]
    if not synteny:
        return None
    params = {**binding.params, **dict.fromkeys(synteny)}
    return _criterion(binding.model_copy(update={"params": params}))


def long_reason(messages: list[ModelMessage]) -> CallFault:
    """A binding after the first bound criterion, with a reason past the cap.

    The pass that continues a stopped pass binds as the arc does.
    """
    continued = _CONTINUATION in head_work_order(messages)
    # A compacted run drops the reply, and the pinned workspace keeps the bind.
    bound = bool(workspace_criteria(instructions_of(messages))) or any(
        reply.resolved_params for reply in criterion_replies(messages)
    )

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        binding = _binding(intended)
        if continued or not bound or binding is None or binding.why is None:
            return None
        why = binding.why.model_copy(update={"reason": LONG_REASON})
        return _criterion(binding.model_copy(update={"why": why}))

    return fault


class _Tested(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wdk_step_id: int
    positive_controls: list[str] = Field(min_length=1)


def repeat_control_test(messages: list[ModelMessage]) -> CallFault:
    """Once the arc's control test answered and the arc moved on, the same step
    again on half its positives."""
    answered = any(
        part.tool_name == CONTROL_TEST for part in tool_return_parts(messages)
    )
    tested = next(
        (
            _Tested.model_validate(part.args_as_dict())
            for part in called_tool_parts(messages)
            if part.tool_name == CONTROL_TEST
        ),
        None,
    )

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        if not answered or tested is None or intended.tool_name == CONTROL_TEST:
            return None
        half = tested.positive_controls[: max(1, len(tested.positive_controls) // 2)]
        return scripted_call(
            CONTROL_TEST, {"wdk_step_id": tested.wdk_step_id, "positive_controls": half}
        )

    return fault


class _DigestArgs(BaseModel):
    model_config = ConfigDict(extra="allow")

    review: VerificationReview | None = None


class _VerifyAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")

    digest: _DigestArgs


def _all_unclear(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's verdict with every sampled gene judged unclear."""
    if intended.tool_name != ANSWER:
        return None
    answer = _VerifyAnswer.model_validate(intended.args_as_dict())
    review = answer.digest.review
    if review is None or not review.sampled_genes:
        return None
    unclear = [
        gene.model_copy(update={"fits": "unclear", "why": "the record does not say"})
        for gene in review.sampled_genes
    ]
    digest = answer.digest.model_copy(
        update={"review": review.model_copy(update={"sampled_genes": unclear})}
    )
    dumped = answer.model_copy(update={"digest": digest})
    return scripted_call(ANSWER, dumped.model_dump(by_alias=True, mode="json"))


class _LeadAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")

    prose: str


def _restated(intended: ToolCallPart, prose: str) -> ToolCallPart:
    return scripted_call(ANSWER, {**intended.args_as_dict(), "prose": prose})


def _stated_count(intended: ToolCallPart) -> re.Match[str] | None:
    if intended.tool_name != ANSWER:
        return None
    return _STRATEGY_COUNT.search(
        _LeadAnswer.model_validate(intended.args_as_dict()).prose
    )


def _transcript_count(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's reply with its gene count named in transcripts."""
    stated = _stated_count(intended)
    if stated is None:
        return None
    prose = stated.string
    wrong = f"{stated['count']} transcripts"
    return _restated(
        intended, f"{prose[: stated.start()]}{wrong}{prose[stated.end() :]}"
    )


def _misstated_count(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's reply with a gene count no step holds: twice the root, plus one."""
    stated = _stated_count(intended)
    if stated is None:
        return None
    root = int(stated["count"].replace(",", ""))
    prose = stated.string
    wrong = f"{2 * root + 1:,} genes"
    return _restated(
        intended, f"{prose[: stated.start()]}{wrong}{prose[stated.end() :]}"
    )


def misnamed_deletion(messages: list[ModelMessage]) -> CallFault:
    """Once the delete card answered, a reply naming the step that stays."""
    deleted = any(part.tool_name == DELETE for part in tool_return_parts(messages))

    def fault(intended: ToolCallPart) -> ToolCallPart | None:
        if not deleted or intended.tool_name != ANSWER:
            return None
        return _restated(intended, MISNAMED_DELETION)

    return fault


def _unbacked_controls(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's reply claiming every positive control of a set one larger."""
    if intended.tool_name != ANSWER:
        return None
    total = len(turn_controls()[0]) + 1
    prose = _LeadAnswer.model_validate(intended.args_as_dict()).prose
    claim = f"It returned {total} of {total} positive controls."
    return _restated(intended, f"{prose} {claim}")


def _sweep_without_controls(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's sweep with no control set and no control ids."""
    if intended.tool_name != SWEEP:
        return None
    unnamed = {"control_set_id", "positive_controls", "negative_controls"}
    args = {k: v for k, v in intended.args_as_dict().items() if k not in unnamed}
    return scripted_call(SWEEP, args)


def _short_card_reply(intended: ToolCallPart) -> ToolCallPart | None:
    """The arc's question card with a reply shorter than a sentence."""
    if intended.tool_name != CONSULT:
        return None
    return scripted_call(CONSULT, {**intended.args_as_dict(), "reply": SHORT_REPLY})


unlisted_search: WrongCall = history_free(lambda: _unlisted_search)
value_as_term: WrongCall = history_free(lambda: _value_as_term)
off_vocabulary: WrongCall = history_free(lambda: _off_vocabulary)
syntenic_left_off: WrongCall = history_free(lambda: _syntenic_left_off)
all_unclear: WrongCall = history_free(lambda: _all_unclear)
transcript_count: WrongCall = history_free(lambda: _transcript_count)
misstated_count: WrongCall = history_free(lambda: _misstated_count)
unbacked_controls: WrongCall = history_free(lambda: _unbacked_controls)
sweep_without_controls: WrongCall = history_free(lambda: _sweep_without_controls)
short_card_reply: WrongCall = history_free(lambda: _short_card_reply)
