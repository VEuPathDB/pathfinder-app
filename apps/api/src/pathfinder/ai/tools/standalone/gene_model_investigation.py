from __future__ import annotations

from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import count_noun, with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.models import AbstractModel, Model

from pathfinder.ai.audit.investigator import (
    GeneModelInvestigation,
    audit_deps_of,
    investigate,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.audit.verdicts import VerdictOrigin

INVESTIGATION_DESCRIPTION = (
    "Investigate whether the gene model of one gene, or of a gene and its "
    "reference gene, is right. A bounded investigator runs the site's single-gene "
    "checks and reads the stored audit evidence, stores one verdict for each "
    "model it judges, and answers with what the reads show. question names the "
    "genes in the researcher's words. The answer's facts and genes are this "
    "turn's, so a reply cites them as references."
)

NO_REQUEST_MODEL = "A gene model is investigated only by a model that answers requests."


def request_model(model: AbstractModel) -> Model:
    match model:
        case Model():
            return model
        case _:
            raise CallRefused(NO_REQUEST_MODEL)


async def investigate_gene_models(
    ctx: RunContext[AgentDeps], question: str, *, origin: VerdictOrigin
) -> ToolReturn[GeneModelInvestigation]:
    deps = audit_deps_of(ctx.deps, origin=origin)
    model = request_model(ctx.model)
    found, usage = await investigate(question, deps=deps, model=model)
    if ctx.deps.meter is not None:
        ctx.deps.meter(usage, model.model_id)
    ctx.deps.turn_markers.record_audit_facts(found.facts)
    ctx.deps.turn_markers.record_resolved_genes(found.records)
    summary = count_noun(len(found.verdicts), "verdict")
    return with_summary(found, f"Investigated: {summary}", ctx=ctx)
