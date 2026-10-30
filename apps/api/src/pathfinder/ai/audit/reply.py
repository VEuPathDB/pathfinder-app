"""The auditor's typed reply, and the text it renders to: the facts its reads hold, then its note."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field, StringConstraints
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.output import OutputContext

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, REPLY_NOTE
from pathfinder.ai.lead.contract_messages import note_facts_message
from pathfinder.domain.reply_note import note_facts, render_note

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
    facts = deps.turn_facts(deps.request)
    shown = [audit.markdown() for audit in facts.reads]
    return "\n\n".join([*shown, render_note(reply.prose, facts)])


def hold_the_reply(ctx: RunContext[AuditDeps], output: AuditReply) -> AuditReply:
    written = note_facts(output.prose, ctx.deps.turn_facts(ctx.deps.request))
    if written and may_refuse(ctx, ctx.deps.reply_refusals):
        ctx.deps.reply_refusals += 1
        raise ModelRetry(note_facts_message(written))
    return output


@dataclass
class HoldTheReply(AbstractCapability[AuditDeps]):
    async def after_output_validate(
        self,
        ctx: RunContext[AuditDeps],
        *,
        output_context: OutputContext,
        output: Any,
    ) -> Any:
        del output_context
        match output:
            case AuditReply():
                return hold_the_reply(ctx, output)
            case _:
                return output
