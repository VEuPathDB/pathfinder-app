from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

KEEP_RECENT_TOOL_PAIRS = 3

_ELIDE_MIN_CHARS = 400
"""Results at or below this stay whole.

A count or an id costs a few tokens to keep and a whole round trip to
re-fetch, so a small result is worth more in history than out of it.
"""

_ELIDE_DIGEST_CHARS = 220

_ELIDED_MARKER = "<elided to control context size"


def _digest(content: object) -> str:
    """Compress a bulky result, keeping the head so its facts survive.

    A stub with no readable head invites the model to re-fetch the same
    data; a head that keeps counts and ids stays answerable from history.
    """
    try:
        rendered = content if isinstance(content, str) else json.dumps(content)
    except TypeError, ValueError:
        rendered = str(content)
    head = rendered[:_ELIDE_DIGEST_CHARS]
    return f"{head}... {_ELIDED_MARKER}; already acted on, do not fetch again>"


def _already_elided(content: object) -> bool:
    """Idempotent: a digest must not be digested again on the next pass."""
    return isinstance(content, str) and content.endswith(
        "already acted on, do not fetch again>"
    )


def _too_small_to_elide(content: object) -> bool:
    try:
        rendered = content if isinstance(content, str) else json.dumps(content)
    except TypeError, ValueError:
        rendered = str(content)
    return len(rendered) <= _ELIDE_MIN_CHARS


def _ordered_tool_call_ids(messages: Sequence[ModelMessage]) -> list[str]:
    out: list[str] = []
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        out.extend(
            part.tool_call_id for part in msg.parts if isinstance(part, ToolCallPart)
        )
    return out


def elide_consumed_tool_results(
    messages: list[ModelMessage],
) -> list[ModelMessage]:
    # Replace older ``ToolReturnPart`` bodies with a stub, keeping the most
    # recent ``KEEP_RECENT_TOOL_PAIRS`` intact. Pairing is preserved
    # (Anthropic/OpenAI reject orphans); only result *content* is shortened.
    call_ids = _ordered_tool_call_ids(messages)
    if len(call_ids) <= KEEP_RECENT_TOOL_PAIRS:
        return list(messages)
    elide_ids = set(call_ids[:-KEEP_RECENT_TOOL_PAIRS])
    return [_elide_returns_in_message(msg, elide_ids) for msg in messages]


def _elide_returns_in_message(
    msg: ModelMessage,
    elide_ids: set[str],
) -> ModelMessage:
    if not isinstance(msg, ModelRequest):
        return msg
    new_parts: list[ModelRequestPart] = []
    changed = False
    for part in msg.parts:
        # Mask any consumed return — including structured (Pydantic / list /
        # dict) content. pydantic-ai keeps the raw object in ``.content`` and
        # serializes it only at request-build time, so an ``isinstance(str)``
        # guard here would skip exactly the heavy discovery payloads
        # (search results, parameter schemas, vocabularies) this is meant to
        # compress. ``content != stub`` keeps it idempotent: once replaced,
        # the stub string compares equal and is left alone.
        if (
            isinstance(part, ToolReturnPart)
            and part.tool_call_id in elide_ids
            and not part.files
            and not _already_elided(part.content)
            and not _too_small_to_elide(part.content)
        ):
            new_parts.append(
                dataclasses.replace(part, content=_digest(part.content)),
            )
            changed = True
        else:
            new_parts.append(part)
    if not changed:
        return msg
    return dataclasses.replace(msg, parts=new_parts)
