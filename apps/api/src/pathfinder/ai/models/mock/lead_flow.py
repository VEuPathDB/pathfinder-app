"""How a Lead arc advances, and the build and edit journeys most arcs share.

An arc is a sequence of calls rebuilt from the run on every step; the next call
is the first one the run has not made. A build the thread refuses ends the turn
instead of verifying.
"""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.models.scripted import (
    called_tool_parts,
    current_turn,
    next_unmade_call,
    scripted_call,
)
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script, Sequence
from pathfinder.ai.models.mock.calls import CLASSIFY, classify, lead_final
from pathfinder.ai.models.mock.reads import (
    added_search_lines,
    frame_is_ready,
    live_count_sentence,
    refusal_of,
    turn_start_instructions,
    verification_prose,
    verified,
)

SUCCESS_PROSE = (
    "**Verified end-to-end.** The strategy framed, built, and verified "
    "cleanly: root size looks right and the leaves are non-empty."
)
FEEDBACK_PROSE = (
    "**Verification found a problem.** The root **returned 0** genes, so a "
    "search is too narrow. Relax it and I will re-verify."
)
# The reply to each refused build, in the words a researcher reads: what
# stopped it, then the question that unblocks it.
_REPLACES = (
    (
        "Nothing was built: this conversation already has a strategy, and a new "
        "build would replace every step."
    ),
    (
        "Which steps do you want me to change, or should I clear the strategy "
        "and start over?"
    ),
)
_NEEDS_ANALYSIS = (
    (
        "Nothing was built: the search the site offers for this is an expression "
        "analysis, and it needs an analysis step first."
    ),
    "Which comparison do you want me to set up?",
)
_NEEDS_A_VALUE = (
    (
        "Nothing was built: the search the site offers for this needs a value "
        "your request does not state."
    ),
    "Which value do you want me to use?",
)
EDIT_PROSE = (
    "**Edited the strategy.** The criterion you named changed; every other "
    "criterion is unchanged, and the steps behind them keep the ids they had."
)

BUILD = "build_strategy"
# The substring of ``build_would_replace_the_strategy`` that names the refusal.
BUILD_REFUSED_MARKER = "build_strategy replaces it"
# The precondition layer withholds the tool on a thread that has a strategy, so
# the turn can meet the same refusal as an absence.
_BUILD_ABSENT_MARKER = "Unknown tool name"
# The substring of ``build_not_ready_message`` for a spec that waits on analyses.
_ANALYSIS_MARKER = "waits for the analysis workflow"
# The Lead's pinned spec, and the words it holds while nothing is framed.
_SPEC_PIN = "## Operational Spec"
_NOTHING_FRAMED = "Not framed yet."


def classified_this_turn(messages: list[ModelMessage]) -> bool:
    return any(
        part.tool_name == CLASSIFY for part in called_tool_parts(current_turn(messages))
    )


def run_sequence(
    messages: list[ModelMessage], sequence: list[ToolCallPart]
) -> ToolCallPart:
    """The next call of this turn's arc.

    The classification is the turn's own: an arc that opens with it re-runs it
    on every turn, so the intent the Lead gates its tools on is never a
    previous turn's.
    """
    if sequence[0].tool_name != CLASSIFY:
        return next_unmade_call(sequence, messages)
    if not classified_this_turn(messages):
        return sequence[0]
    return next_unmade_call(sequence[1:], messages)


def lead(sequence: Sequence) -> Script:
    """The Lead script that plays ``sequence``."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        return run_sequence(messages, sequence(messages))

    return script


def thread_is_framed(messages: list[ModelMessage]) -> bool:
    """Whether the Lead's pinned spec held a framed request when the turn
    began, so a frame of this turn's own does not count."""
    pinned = turn_start_instructions(messages)
    return _SPEC_PIN in pinned and _NOTHING_FRAMED not in pinned


def build_classification(messages: list[ModelMessage]) -> str:
    """A build extends the draft the Lead's pinned spec states, else starts one."""
    return "extend_strategy" if thread_is_framed(messages) else "new_strategy"


def build_refused(messages: list[ModelMessage]) -> bool:
    refusal = refusal_of(messages, BUILD)
    return refusal is not None and (
        BUILD_REFUSED_MARKER in refusal or _BUILD_ABSENT_MARKER in refusal
    )


def _unbuilt(messages: list[ModelMessage]) -> ToolCallPart | None:
    """The reply to a build the tool refused: what stopped it and the one
    question that unblocks it, in plain words, with nothing checked. None when
    the build was not refused."""
    refusal = refusal_of(messages, BUILD)
    if refusal is None:
        return None
    if build_refused(messages):
        said, asked = _REPLACES
    elif _ANALYSIS_MARKER in refusal:
        said, asked = _NEEDS_ANALYSIS
    else:
        said, asked = _NEEDS_A_VALUE
    return lead_final(f"{said} {asked}", "await_user", questions=[asked])


def written_tail(messages: list[ModelMessage], count: str | None = None) -> str:
    """What a reply that wrote the strategy ends on: each search the turn
    added with its reason, then ``count``, else the count the site answers now."""
    count = count or live_count_sentence(messages)
    lines = added_search_lines(messages)
    return f"\n\n{lines}\n\n{count}" if lines else f" {count}"


def _checked(
    messages: list[ModelMessage],
    success: str,
    failure: str,
    *,
    changed: bool = True,
) -> list[ToolCallPart]:
    """Verify, read the count the site answers now, and state it beside each
    search the turn added, named with its reason."""
    tail = written_tail(messages)
    final = (
        lead_final(f"{success}{tail}", "complete", strategy_changed=changed)
        if verified(messages)
        else lead_final(f"{failure}{tail}", "await_user", strategy_changed=changed)
    )
    return [
        scripted_call("verify_strategy", {"reason": "mock verification"}),
        scripted_call("get_live_strategy_state", {}),
        final,
    ]


def build_journey(
    messages: list[ModelMessage],
    *,
    classification: str | None = None,
    success: str = SUCCESS_PROSE,
    failure: str = FEEDBACK_PROSE,
) -> list[ToolCallPart]:
    """Frame, build and verify; a refused build answers with the edit route."""
    head = [
        classify(classification or build_classification(messages)),
        scripted_call("frame_problem", {"reason": "mock frame"}),
        scripted_call(BUILD, {}),
    ]
    unbuilt = _unbuilt(messages)
    if unbuilt is not None:
        return [*head, unbuilt]
    return [*head, *_checked(messages, success, failure)]


def edit_journey(
    messages: list[ModelMessage], *, failure: str = FEEDBACK_PROSE
) -> list[ToolCallPart]:
    """Edit the strategy the thread holds and verify what changed."""
    return [
        classify("edit_strategy"),
        scripted_call("edit_strategy", {"reason": "mock edit"}),
        *_checked(messages, EDIT_PROSE, failure),
    ]


def build_when_framed(
    messages: list[ModelMessage], prose: Callable[[list[ModelMessage]], str]
) -> list[ToolCallPart]:
    """Frame; build and check a spec the pass made ready, else answer with
    ``prose`` and build nothing."""
    if not frame_is_ready(messages):
        return framed_only(messages, prose)
    head = [*framed_only(messages, prose)[:2], scripted_call(BUILD, {})]
    unbuilt = _unbuilt(messages)
    if unbuilt is not None:
        return [*head, unbuilt]
    return [*head, *_checked(messages, SUCCESS_PROSE, FEEDBACK_PROSE)]


def check_or_build(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Check the strategy the thread holds, which changes nothing, else build
    one and check it, and answer with what the check found."""
    found = verification_prose(messages) or SUCCESS_PROSE
    if thread_is_framed(messages):
        checked = _checked(messages, found, found, changed=False)
        return [classify("extend_strategy"), *checked]
    return build_journey(messages, success=found, failure=found)


def extend_or_build(
    messages: list[ModelMessage], *, failure: str = FEEDBACK_PROSE
) -> list[ToolCallPart]:
    """Grow the strategy the thread holds, else build the whole spec fresh."""
    if thread_is_framed(messages):
        return edit_journey(messages, failure=failure)
    return build_journey(messages, failure=failure)


def framed_only(
    messages: list[ModelMessage], prose: Callable[[list[ModelMessage]], str]
) -> list[ToolCallPart]:
    """Frame and answer with what the pass found, building nothing."""
    return [
        classify("new_strategy"),
        scripted_call("frame_problem", {"reason": "mock frame"}),
        lead_final(prose(messages), "await_user"),
    ]
