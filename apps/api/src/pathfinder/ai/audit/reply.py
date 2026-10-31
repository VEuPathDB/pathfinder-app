"""The auditor's typed reply, and the text it renders to: the facts its reads hold, then its note."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, StringConstraints

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, REPLY_NOTE
from pathfinder.domain.reply_note import render_note

_REPLY_MIN_CHARS = 20


class AuditReply(CamelModel):
    prose: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=_REPLY_MIN_CHARS,
            max_length=PROSE_MAX_CHARS,
        ),
        Field(description=f"Your reply. {REPLY_NOTE}"),
    ]


def reply_text(reply: AuditReply, deps: AuditDeps) -> str:
    facts = deps.turn_facts()
    shown = [audit.markdown() for audit in facts.reads]
    return "\n\n".join([*shown, render_note(reply.prose, facts)])
