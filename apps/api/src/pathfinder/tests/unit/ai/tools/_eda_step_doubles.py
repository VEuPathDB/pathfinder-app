"""The analysis document and the commit stand-ins the eda_step cases share."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
    EdaVariableSpec,
)

from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.eda_doubles import ANALYSIS_ID, SPECIES_VARIABLE
from pathfinder.tests._support.eda_wire import PHENOTYPE_DATASET, PHENOTYPE_ENTITY

WDK_STRATEGY_ID = 330423363

Commit = Callable[..., Awaitable[CommitResult]]


async def bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def unbound(_ctx: object) -> ConversationAnalysisView | None:
    return None


def _computation() -> EdaComputation:
    return EdaComputation(
        computation_id="c1",
        descriptor=EdaComputationDescriptor(
            configuration=EdaDifferentialExpressionConfig(
                identifier_variable=EdaVariableSpec(
                    entity_id=PHENOTYPE_ENTITY, variable_id="VAR_gene"
                ),
                value_variable=EdaVariableSpec(
                    entity_id=PHENOTYPE_ENTITY, variable_id="VAR_counts"
                ),
                comparator=EdaComparator(
                    variable=EdaVariableSpec(
                        entity_id=PHENOTYPE_ENTITY, variable_id="VAR_state"
                    ),
                    group_a=[EdaLabeledRange(label="febrile")],
                    group_b=[EdaLabeledRange(label="normal")],
                ),
            )
        ),
    )


def analysis_detail(*, with_computation: bool) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="berghei subset",
        study_id=PHENOTYPE_DATASET,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaStringSetFilter(
                        entity_id=PHENOTYPE_ENTITY,
                        variable_id=SPECIES_VARIABLE,
                        string_set=["P. berghei"],
                    )
                ]
            ),
            computations=[_computation()] if with_computation else [],
        ),
    )


async def read_detail(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
    assert analysis_id == ANALYSIS_ID
    return analysis_detail(with_computation=False)


async def read_detail_with_computation(
    _site: str, *, analysis_id: str
) -> EdaAnalysisDetail:
    assert analysis_id == ANALYSIS_ID
    return analysis_detail(with_computation=True)


def recording_commit(
    applied: list[Any],
    *,
    wdk_url: str | None = None,
    dropped: list[str] | None = None,
) -> Commit:
    """A commit that records the operations and reports a landed strategy."""

    async def commit(*, deps: object, ops: list[Any]) -> CommitResult:
        assert deps is not None
        applied.append(ops)
        return CommitResult(
            description="added a step",
            dropped_step_ids=list(dropped or []),
            sync_result=SyncResult(
                wdk_strategy_id=WDK_STRATEGY_ID,
                wdk_url=wdk_url,
                root_step_id=1,
                counts={},
                root_count=132,
                zero_step_ids=[],
                step_count=1,
            ),
        )

    return commit


def pushing_commit(
    applied: list[Any],
    *,
    session: StrategySession,
    count: int,
    wdk_step_id: int = 8811,
) -> Commit:
    """A commit that lands the step and reads its size, as the real one does."""

    async def commit(*, deps: object, ops: list[Any]) -> CommitResult:
        assert deps is not None
        applied.append(ops)
        graph = session.get_graph(None)
        assert graph is not None
        apply_operation(graph, ops[0])
        step_id = ops[0].step.id
        sync_state = ensure_sync_state(session)
        sync_state.wdk_step_ids[step_id] = wdk_step_id
        sync_state.wdk_strategy_id = WDK_STRATEGY_ID
        return CommitResult(
            description="added a step",
            sync_result=SyncResult(
                wdk_strategy_id=WDK_STRATEGY_ID,
                wdk_url=None,
                root_step_id=wdk_step_id,
                counts={step_id: count},
                root_count=count,
                zero_step_ids=[],
                step_count=1,
            ),
        )

    return commit
