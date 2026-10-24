"""The auditor's typed reply, the text it renders to, and the reference contract it is held to."""

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
from pathfinder.ai.graph.note_labels import note_label
from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, REPLY_REFERENCES
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import (
    prose_faults,
    shown_reply,
)

_REPLY_MIN_CHARS = 20


class AuditReply(CamelModel):
    prose: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=_REPLY_MIN_CHARS,
            max_length=PROSE_MAX_CHARS,
        ),
        Field(description=f"Your reply. {REPLY_REFERENCES}"),
    ]


def reply_text(reply: AuditReply, deps: AuditDeps) -> str:
    return shown_reply(reply.prose, deps.turn_facts(deps.request), note_label())


def hold_the_reply(ctx: RunContext[AuditDeps], output: AuditReply) -> AuditReply:
    faults = prose_faults(output.prose, ctx.deps.turn_facts(ctx.deps.request))
    if faults and may_refuse(ctx, ctx.deps.reply_refusals):
        ctx.deps.reply_refusals += 1
        raise ModelRetry(unrendered_prose_message(faults))
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
