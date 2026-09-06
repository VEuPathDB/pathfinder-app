"""Read-only workbench experiment tools.

Each tool reads the experiment that the chat is associated with. A chat without
an experiment gets an error result, not empty data.
"""

from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._workbench_models import (
    ClassificationCounts,
    ConfidenceScoresResult,
    EnrichmentResultsResponse,
    EvaluationSummaryResult,
    ExperimentConfigResult,
    GeneListResult,
    SampleGeneIds,
    WorkbenchError,
)
from pathfinder.services.experiment.types import Experiment
from pathfinder.services.workbench.experiments import get_experiment

type WorkbenchRead[T] = ToolReturn[T | WorkbenchError]


def _unavailable[T](
    ctx: RunContext[AgentDeps],
    error: str,
) -> WorkbenchRead[T]:
    """The read has nothing to report, and the error says why."""
    return with_summary(
        WorkbenchError(error=error),
        error,
        ctx=ctx,
        status="warn",
    )


async def _get_experiment(ctx: RunContext[AgentDeps]) -> Experiment | None:
    experiment_id = ctx.deps.experiment_id
    if not experiment_id:
        return None
    return await get_experiment(experiment_id)


async def get_evaluation_summary(
    ctx: RunContext[AgentDeps],
) -> WorkbenchRead[EvaluationSummaryResult]:
    """Classification metrics, confusion counts, and sample gene IDs."""
    exp = await _get_experiment(ctx)
    if not exp:
        return _unavailable(ctx, "Conversation has no associated experiment")
    if not exp.metrics:
        return _unavailable(ctx, "Experiment has no evaluation metrics yet")

    counts = ClassificationCounts(
        true_positives=len(exp.true_positive_genes),
        false_positives=len(exp.false_positive_genes),
        false_negatives=len(exp.false_negative_genes),
        true_negatives=len(exp.true_negative_genes),
    )
    classified = (
        counts.true_positives
        + counts.false_positives
        + counts.false_negatives
        + counts.true_negatives
    )
    return with_summary(
        EvaluationSummaryResult(
            metrics=exp.metrics,
            classification_counts=counts,
            sample_gene_ids=SampleGeneIds(
                true_positives=[g.id for g in exp.true_positive_genes[:5]],
                false_positives=[g.id for g in exp.false_positive_genes[:5]],
                false_negatives=[g.id for g in exp.false_negative_genes[:5]],
                true_negatives=[g.id for g in exp.true_negative_genes[:5]],
            ),
            status=exp.status,
        ),
        f"{classified} classified genes",
        ctx=ctx,
        status="ok" if classified else "empty",
    )


async def get_enrichment_results(
    ctx: RunContext[AgentDeps],
) -> WorkbenchRead[EnrichmentResultsResponse]:
    """GO term, pathway, and word enrichment for the current experiment."""
    exp = await _get_experiment(ctx)
    if not exp:
        return _unavailable(ctx, "Conversation has no associated experiment")
    if not exp.enrichment_results:
        return _unavailable(ctx, "No enrichment results available for this experiment")

    return with_summary(
        EnrichmentResultsResponse(
            enrichment_results=exp.enrichment_results,
            count=len(exp.enrichment_results),
        ),
        f"{len(exp.enrichment_results)} enrichment analyses",
        ctx=ctx,
    )


async def get_confidence_scores(
    ctx: RunContext[AgentDeps],
) -> WorkbenchRead[ConfidenceScoresResult]:
    """Cross-validation confidence scores for the current experiment."""
    exp = await _get_experiment(ctx)
    if not exp:
        return _unavailable(ctx, "Conversation has no associated experiment")
    if not exp.cross_validation:
        return _unavailable(
            ctx, "No cross-validation results available for this experiment"
        )

    return with_summary(
        ConfidenceScoresResult(cross_validation=exp.cross_validation),
        f"{len(exp.cross_validation.folds)} cross-validation folds",
        ctx=ctx,
    )


async def get_experiment_config(
    ctx: RunContext[AgentDeps],
) -> WorkbenchRead[ExperimentConfigResult]:
    """Experiment configuration, status, and WDK strategy/step IDs."""
    exp = await _get_experiment(ctx)
    if not exp:
        return _unavailable(ctx, "Conversation has no associated experiment")

    return with_summary(
        ExperimentConfigResult(
            config=exp.config,
            status=exp.status,
            wdk_strategy_id=exp.wdk_strategy_id,
            wdk_step_id=exp.wdk_step_id,
            notes=exp.notes,
            created_at=exp.created_at,
            completed_at=exp.completed_at,
        ),
        f"Experiment is {exp.status}",
        ctx=ctx,
    )


async def get_result_gene_lists(
    ctx: RunContext[AgentDeps],
    classification: str,
    limit: int = 50,
) -> WorkbenchRead[GeneListResult]:
    """Gene IDs for a classification category (tp/fp/fn/tn).

    Args:
        classification: Classification category: 'tp', 'fp', 'fn', or 'tn'.
        limit: Maximum number of gene IDs to return (max 200).
    """
    valid: set[str] = {"tp", "fp", "fn", "tn"}
    if classification not in valid:
        return _unavailable(
            ctx,
            f"Invalid classification '{classification}'. "
            f"Must be one of: {', '.join(sorted(valid))}",
        )

    exp = await _get_experiment(ctx)
    if not exp:
        return _unavailable(ctx, "Conversation has no associated experiment")

    gene_list = {
        "tp": exp.true_positive_genes,
        "fp": exp.false_positive_genes,
        "fn": exp.false_negative_genes,
        "tn": exp.true_negative_genes,
    }[classification]

    capped = min(limit, 200)
    selected = gene_list[:capped]

    return with_summary(
        GeneListResult(
            classification=classification,
            genes=selected,
            returned=len(selected),
            total=len(gene_list),
        ),
        f"{len(selected)} of {len(gene_list)} {classification} genes",
        ctx=ctx,
        status="ok" if selected else "empty",
    )
