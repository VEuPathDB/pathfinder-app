"""A sub-agent dispatch is rendered as one card, on every path including failure.

The Lead's ``frame_problem`` call reaches the client as a ``data-sub-agent-call``
card; its native tool chunks are suppressed so the raw tool card does not render
alongside it. The suppression list was written from the chunk types seen on the
happy path, so ``ToolOutputErrorChunk`` was never in it.

When a run raises, pydantic-ai closes its pending tool calls by emitting a tool
output for each one (``_event_stream.py``: "Tool execution was interrupted by an
error."). That native error chunk leaked through for a call whose *input* chunks
had been suppressed, so the client had no invocation to attach it to:

    Response failed: No tool invocation found for tool call ID
    "call_EXAMPLE".

That id was the ``frame_problem`` dispatch. The Vercel AI SDK throws
``UIMessageStreamError`` on the unmatched id and marks the whole response
failed, so an interruption we could have shown inside the card killed the turn
instead. It reproduces on every abnormal ending: branch, revert, cancel, and
hitting the tool-call ceiling.

Suppression is therefore defined by *what a chunk refers to*, not by a list of
chunk types someone remembered to extend. ``test_every_tool_chunk_type_is_classified``
is the part that keeps it fixed: it fails if pydantic-ai adds a tool chunk type
nobody classified, instead of letting it leak into a user-visible crash.
"""

from __future__ import annotations

import inspect

from pydantic import BaseModel
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.ui.vercel_ai import response_types
from pydantic_ai.ui.vercel_ai.response_types import (
    TextDeltaChunk,
    ToolApprovalRequestChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputErrorChunk,
)

from pathfinder.ai.graph._lead_events import (
    _CHUNKS_EXEMPT_FROM_SUPPRESSION,
    _TOOL_CALL_CHUNKS,
    is_suppressed_sub_agent_chunk,
    sub_agent_result_failed,
)

_CALL_ID = "call_EXAMPLE"


def _claim_the_dispatch() -> dict[str, str]:
    """Prime the id map the way a real stream does: the input chunk arrives
    first and carries the tool name."""
    claimed: dict[str, str] = {}
    is_suppressed_sub_agent_chunk(
        ToolInputStartChunk(tool_call_id=_CALL_ID, tool_name="frame_problem"),
        claimed,
    )
    return claimed


class TestTheFailurePath:
    def test_a_tool_output_error_for_a_dispatch_is_suppressed(self) -> None:
        claimed = _claim_the_dispatch()

        suppressed = is_suppressed_sub_agent_chunk(
            ToolOutputErrorChunk(tool_call_id=_CALL_ID, error_text="interrupted"),
            claimed,
        )

        assert suppressed, (
            "the client has no native invocation for a dispatch call, so this "
            "chunk makes the AI SDK throw and fail the whole response"
        )

    def test_the_success_path_is_still_suppressed(self) -> None:
        claimed = _claim_the_dispatch()

        assert is_suppressed_sub_agent_chunk(
            ToolOutputAvailableChunk(tool_call_id=_CALL_ID, output="done"), claimed
        )


class TestOrdinaryToolsAreUntouched:
    def test_a_normal_tool_output_error_passes_through(self) -> None:
        # `get_strategy` renders as a real tool card, so its chunks must reach
        # the client on the failure path too.
        claimed = _claim_the_dispatch()

        assert not is_suppressed_sub_agent_chunk(
            ToolOutputErrorChunk(tool_call_id="call_other", error_text="boom"),
            claimed,
        )

    def test_a_normal_tool_input_passes_through(self) -> None:
        claimed: dict[str, str] = {}

        assert not is_suppressed_sub_agent_chunk(
            ToolInputStartChunk(tool_call_id="call_other", tool_name="get_strategy"),
            claimed,
        )

    def test_a_non_tool_chunk_passes_through(self) -> None:
        claimed = _claim_the_dispatch()

        assert not is_suppressed_sub_agent_chunk(
            TextDeltaChunk(id="t1", delta="hello"), claimed
        )


class TestEveryDispatchToolName:
    def test_each_sub_agent_tool_claims_its_id(self) -> None:
        for name in (
            "frame_problem",
            "build_strategy",
            "recover_failed_steps",
            "verify_strategy",
        ):
            claimed: dict[str, str] = {}
            is_suppressed_sub_agent_chunk(
                ToolInputStartChunk(tool_call_id=f"call_{name}", tool_name=name),
                claimed,
            )

            assert is_suppressed_sub_agent_chunk(
                ToolOutputErrorChunk(
                    tool_call_id=f"call_{name}", error_text="interrupted"
                ),
                claimed,
            ), f"{name} leaks a native error chunk"


def test_every_tool_chunk_type_is_classified() -> None:
    """The guard that keeps this from recurring.

    ``ToolOutputErrorChunk`` was missing because the list enumerated the chunk
    types someone had seen, and nothing noticed the gap until it crashed a real
    turn. Every chunk pydantic-ai defines with a ``tool_call_id`` must be either
    suppressible or deliberately exempt, so a new one fails here rather than in
    a user's browser.
    """
    carries_tool_call_id = {
        obj
        for _, obj in inspect.getmembers(response_types, inspect.isclass)
        if issubclass(obj, BaseModel) and "tool_call_id" in obj.model_fields
    }

    unclassified = (
        carries_tool_call_id
        - set(_TOOL_CALL_CHUNKS)
        - set(_CHUNKS_EXEMPT_FROM_SUPPRESSION)
    )

    assert not unclassified, (
        f"pydantic-ai defines tool chunk(s) nobody classified: "
        f"{sorted(c.__name__ for c in unclassified)}. Add each to "
        f"_TOOL_CALL_CHUNKS (suppress with the dispatch) or to "
        f"_CHUNKS_EXEMPT_FROM_SUPPRESSION (must reach the client)."
    )


def test_approval_chunks_are_exempt_so_the_user_can_answer() -> None:
    # Suppressing an approval request would hang the turn on a question the
    # user never sees.
    assert ToolApprovalRequestChunk in _CHUNKS_EXEMPT_FROM_SUPPRESSION
    assert set(_CHUNKS_EXEMPT_FROM_SUPPRESSION).isdisjoint(_TOOL_CALL_CHUNKS)


class TestTheCardTellsTheTruth:
    """Suppressing the orphan chunk must not turn a crash into a false success.

    pydantic-ai closes an interrupted tool call with
    ``ToolReturnPart(outcome="failed")``, not a ``RetryPromptPart``. Reading
    only the retry case rendered an interrupted sub-agent as "completed".
    """

    def test_an_interrupted_call_is_a_failure(self) -> None:
        interrupted = ToolReturnPart(
            tool_name="frame_problem",
            content="Tool execution was interrupted by an error.",
            tool_call_id=_CALL_ID,
            outcome="failed",
        )

        assert sub_agent_result_failed(interrupted)

    def test_a_real_result_is_not_a_failure(self) -> None:
        done = ToolReturnPart(
            tool_name="frame_problem",
            content="spec assembled",
            tool_call_id=_CALL_ID,
        )

        assert not sub_agent_result_failed(done)

    def test_a_retry_prompt_is_a_failure(self) -> None:
        retry = RetryPromptPart(content="try again", tool_call_id=_CALL_ID)

        assert sub_agent_result_failed(retry)
