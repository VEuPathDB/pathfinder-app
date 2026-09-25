"""The open analysis, turned into a step in the researcher's strategy."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.types import JSONObject
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.eda import EdaAnalysisDetail, EdaNewAnalysis
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding, AnalysisKind
from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.domain.strategy.operations.types import AttachNewRoot
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.eda.binding import open_analysis_or_conflict
from pathfinder.services.eda.compute import (
    VolcanoThresholds,
    analysis_comparison,
    stored_volcano_cut,
)
from pathfinder.services.eda.direction import direction_sentence
from pathfinder.services.eda.export import analysis_binding, eda_step_request
from pathfinder.services.eda.gene_subset import refuse_a_subset_that_selects_no_genes


def eda_search_name(*, is_compute_backed: bool) -> str:
    """The generic EDA-backed search for each of the two exports."""
    return COMPUTE_QUERY if is_compute_backed else SUBSET_QUERY


@dataclass(frozen=True, slots=True)
class EdaStepPlan:
    """The step one export produces, which of the two exports it is, and what
    it selects."""

    node: StrategyStepNode
    is_compute_backed: bool
    binding: AnalysisBinding

    @property
    def stamped(self) -> StampedKind:
        """The plugin that reads the step's document: the export decides it."""
        return StampedKind(
            search_name=self.node.search_name,
            kind=AnalysisKind.COMPUTE
            if self.is_compute_backed
            else AnalysisKind.SUBSET,
        )


def eda_step_node(
    analysis: EdaAnalysisDetail,
    *,
    dataset_id: str,
    thresholds: VolcanoThresholds | None = None,
) -> EdaStepPlan:
    """The step this analysis exports. Thresholds select the compute export.

    Each export runs the generic search of its kind. A compute export is named
    by the genes its direction keeps.
    """
    is_compute_backed = thresholds is not None
    request = eda_step_request(
        analysis,
        dataset_id=dataset_id,
        effect_size_threshold=(
            None if thresholds is None else thresholds.effect_size_threshold
        ),
        significance_threshold=(
            None if thresholds is None else thresholds.significance_threshold
        ),
        effect_direction=(
            "upAndDown" if thresholds is None else thresholds.effect_direction
        ),
    )
    node = StrategyStepNode(
        search_name=eda_search_name(is_compute_backed=is_compute_backed),
        parameters={
            name: StringValue(value=value)
            for name, value in request.wdk_parameters().items()
        },
        display_name=(
            analysis.display_name or None
            if thresholds is None
            else direction_sentence(
                analysis_comparison(analysis), thresholds.effect_direction
            )
        ),
    )
    spec = EdaNewAnalysis.model_validate_json(request.eda_analysis_spec)
    binding = analysis_binding(
        dataset_id,
        spec,
        node.parameters,
        reads_a_volcano=is_compute_backed,
    )
    return EdaStepPlan(node=node, is_compute_backed=is_compute_backed, binding=binding)


async def export_analysis_step(
    *,
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    reads_the_volcano: bool,
) -> JSONObject:
    """Add the thread's open analysis to its strategy, and read it back.

    A volcano export writes the cut the analysis stores, so an edit the site
    made is the one exported. The answer is the refreshed strategy the strategy
    routes already return. A subset export clears the agent's gene check.
    """
    binding, analysis = await open_analysis_or_conflict(conversation_id=conversation_id)
    thresholds = stored_volcano_cut(analysis) if reads_the_volcano else None
    if thresholds is None:
        await refuse_a_subset_that_selects_no_genes(
            binding.site_id, dataset_id=binding.dataset_id, analysis=analysis
        )
    plan = eda_step_node(
        analysis,
        dataset_id=binding.dataset_id,
        thresholds=thresholds,
    )
    refreshed = await ConversationService(session).apply_operation(
        conversation_id,
        user_id,
        site_id=binding.site_id,
        op=AddLeafOp(step=plan.node, attach=AttachNewRoot()),
        analysis_kinds={plan.node.id: plan.stamped},
    )
    return refreshed.model_dump(by_alias=True, mode="json")
