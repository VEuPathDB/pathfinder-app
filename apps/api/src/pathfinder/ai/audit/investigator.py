"""The investigator: one bounded agent run that judges a gene model and stores its verdicts."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.audit.charges import charge_run
from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES, build_check_toolset
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.instructions import INVESTIGATOR_INSTRUCTIONS
from pathfinder.ai.audit.run_tools import READ_TOOL_NAMES, build_read_toolset
from pathfinder.ai.audit.verdict_tool import (
    unheld_cites_message,
    unheld_genomes,
    unheld_genomes_message,
)
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.domain.audit.verdicts import MAX_CARD, GeneModelVerdict, VerdictOrigin
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.services.audit.verdicts import record_verdict

INVESTIGATION_LIMITS = UsageLimits(request_limit=24, tool_calls_limit=24)
BUDGET_ANSWER = "The investigation stopped at its budget before it reached a verdict."
MAX_VERDICTS = 8


class GeneModelInvestigation(CamelModel):
    model_config = ConfigDict(frozen=True)

    answer: str = Field(
        min_length=1,
        max_length=MAX_CARD,
        description="What the reads show about the model, as the judging rules write it.",
    )
    verdicts: tuple[GeneModelVerdict, ...] = Field(
        max_length=MAX_VERDICTS,
        description="One verdict for each model you judged, each citing its reads.",
    )
    facts: SkipJsonSchema[tuple[StatisticFact, ...]] = ()
    records: SkipJsonSchema[tuple[ReadRecord, ...]] = ()
    runs: SkipJsonSchema[tuple[UUID, ...]] = ()


def _cites_held(
    ctx: RunContext[AuditDeps], output: GeneModelInvestigation
) -> GeneModelInvestigation:
    held = ctx.deps.held_reads()
    unheld = [cite for v in output.verdicts for cite in v.unheld_cites(held)]
    if unheld:
        raise ModelRetry(unheld_cites_message(unheld))
    genomes = unheld_genomes(ctx.deps, output.verdicts)
    if genomes:
        raise ModelRetry(unheld_genomes_message(genomes))
    return output


def build_investigator_agent() -> Agent[AuditDeps, GeneModelInvestigation]:
    agent = Agent(
        output_type=GeneModelInvestigation,
        deps_type=AuditDeps,
        instructions=INVESTIGATOR_INSTRUCTIONS,
        toolsets=[build_check_toolset(), build_read_toolset()],
        capabilities=agent_capabilities(
            [SiteReadFailures[AuditDeps](reads=CHECK_TOOL_NAMES | READ_TOOL_NAMES)]
        ),
        retries=3,
        name="investigator",
        defer_model_check=True,
    )
    agent.output_validator(_cites_held)
    return agent


def audit_deps_of(deps: AgentDeps, *, origin: VerdictOrigin) -> AuditDeps:
    return AuditDeps(
        site_id=deps.site_id,
        user_id=deps.user_id,
        conversation_id=deps.conversation_id,
        origin=origin,
    )


def _with_reads(
    found: GeneModelInvestigation, deps: AuditDeps
) -> GeneModelInvestigation:
    return found.model_copy(
        update={
            "facts": tuple(deps.facts),
            "records": tuple(deps.records),
            "runs": tuple(deps.runs),
        }
    )


async def investigate(
    question: str, *, deps: AuditDeps, model: Model, usage: RunUsage
) -> GeneModelInvestigation:
    owner = deps.caller.user_id
    try:
        result = await build_investigator_agent().run(
            question,
            deps=deps,
            model=model,
            usage=usage,
            usage_limits=INVESTIGATION_LIMITS,
        )
    except UsageLimitExceeded:
        stopped = GeneModelInvestigation(answer=BUDGET_ANSWER, verdicts=())
        return _with_reads(stopped, deps)
    finally:
        await charge_run(owner, usage, model, model_id=model.model_id)
    found = result.output
    for verdict in found.verdicts:
        await record_verdict(
            caller=deps.caller,
            origin=deps.origin,
            verdict=verdict,
            model_id=model.model_name,
        )
    return _with_reads(found, deps)
