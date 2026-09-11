"""What the deterministic scripts read from a run history the runtime compacts.

Compaction drops the middle of a run and carries what happened as a digest on
the head request, so a script that reads the newest user text or the visible
calls sees neither its work order nor its own progress.
"""

from __future__ import annotations

import re

from assistant_core.models.scripted import called_tool_parts, user_texts
from pydantic_ai.messages import ModelMessage

_DIGEST_CALL = re.compile(r"^- (?P<tool>[a-z_]+)\(.*\) -> ")


def head_work_order(messages: list[ModelMessage]) -> str:
    """The prompt the run opened with.

    A digest is appended to the same request, so the work order is the first
    user text of the head and never the last one of the run.
    """
    texts = user_texts(messages[:1])
    return texts[0] if texts else ""


def acted_tool_names(messages: list[ModelMessage]) -> frozenset[str]:
    """Every tool the run has called, the calls a digest records included."""
    names = {part.tool_name for part in called_tool_parts(messages)}
    for text in user_texts(messages):
        names.update(
            match.group("tool")
            for line in text.splitlines()
            if (match := _DIGEST_CALL.match(line))
        )
    return frozenset(names)
