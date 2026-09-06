"""The open analysis, turned into a step in the researcher's strategy."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from assistant_core.platform.types import JSONObject
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters.values import StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.operations import AddLeafOp
from veupathdb.domain.strategy.operations.types import AttachNewRoot
from veupathdb.eda.models import EdaAnalysisDetail
from veupathdb_mcp.catalog.eda_backed import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.services.conversations.service import ConversationService
from pathfinder.services.eda.binding import open_analysis_or_conflict
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import eda_step_request


def eda_search_name(*, is_compute_backed: bool) -> str:
    """The generic EDA-backed search for each of the two exports."""
    return COMPUTE_QUERY if is_compute_backed else SUBSET_QUERY


@dataclass(frozen=True, slots=True)
class EdaStepPlan:
    """The step one export produces, and which of the two exports it is."""

    node: StrategyStepNode
    is_compute_backed: bool


def eda_step_node(
    analysis: EdaAnalysisDetail,
    *,
    dataset_id: str,
    thresholds: VolcanoThresholds | None = None,
    search_name: str | None = None,
) -> EdaStepPlan:
    """The step this analysis exports. Thresholds select the compute export."""
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
        search_name=search_name or eda_search_name(is_compute_backed=is_compute_backed),
        parameters={
            name: StringValue(value=value)
            for name, value in request.wdk_parameters().items()
        },
        display_name=analysis.display_name or None,
    )
    return EdaStepPlan(node=node, is_compute_backed=is_compute_backed)


async def export_analysis_step(
    *,
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    thresholds: VolcanoThresholds | None = None,
) -> JSONObject:
    """Add the thread's open analysis to its strategy, and read it back.

    The answer is the refreshed strategy the strategy routes already return,
    so the tab parses it with the reader it already has.
    """
    binding, analysis = await open_analysis_or_conflict(conversation_id=conversation_id)
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
    )
    return refreshed.model_dump(by_alias=True, mode="json")
