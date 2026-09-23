"""The analysis document and the commit stand-ins the eda_step cases share."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaFilter,
    EdaLabeledRange,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaSubsetDescriptor,
    EdaVariableSpec,
)

from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.eda import gene_subset
from pathfinder.services.eda.authoring import SubsetCount
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    permission_entry,
    phenotype_study,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    fixture,
)

WDK_STRATEGY_ID = 330423363

# The recorded RNA-Seq study: samples, and the per-sample gene counts that
# carry the gene id, so the counts entity is the gene entity.
SAMPLE_ENTITY = "ENT_8151325d"
COUNTS_ENTITY = "ENT_fd574cd6"
TEMPERATURE_VARIABLE = "VAR_081ab087"
GENE_ID_VARIABLE = "VEUPATHDB_GENE_ID"

# The refusal of one sample filter and no computation, as both exports word it.
SAMPLE_ONLY_REFUSAL = (
    "The open analysis holds 1 filter on Sample and 0 computations, and no "
    "filter on the gene entity pfal3D7 htseq counts (ENT_fd574cd6). A step "
    "exports genes, and a subset of another entity selects no genes, so "
    "nothing was written. Call run_eda_compute to run the comparison and "
    "export the genes that pass its thresholds, or call set_eda_filters "
    "with a filter on pfal3D7 htseq counts."
)

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


def _computation(group_a: Sequence[str], group_b: Sequence[str]) -> EdaComputation:
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
                    group_a=[EdaLabeledRange(label=label) for label in group_a],
                    group_b=[EdaLabeledRange(label=label) for label in group_b],
                ),
            )
        ),
    )


def _berghei() -> list[EdaFilter]:
    return [
        EdaStringSetFilter(
            entity_id=PHENOTYPE_ENTITY,
            variable_id=SPECIES_VARIABLE,
            string_set=["P. berghei"],
        )
    ]


def analysis_detail(
    *,
    with_computation: bool,
    group_a: Sequence[str] = ("febrile",),
    group_b: Sequence[str] = ("normal",),
    filters: Sequence[EdaFilter] | None = None,
) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="berghei subset",
        study_id=PHENOTYPE_DATASET,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=_berghei() if filters is None else list(filters)
            ),
            computations=([_computation(group_a, group_b)] if with_computation else []),
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


async def de_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    """The recorded RNA-Seq study, as the catalog resolves a dataset id."""
    detail = EdaStudyDetailResponse.model_validate(fixture("study_detail_de")).study
    return permission_entry(), detail


def sample_filter() -> EdaStringSetFilter:
    """A filter on the sample entity, which selects samples and no gene."""
    return EdaStringSetFilter(
        entity_id=SAMPLE_ENTITY,
        variable_id=TEMPERATURE_VARIABLE,
        string_set=["febrile"],
    )


def gene_filter() -> EdaStringSetFilter:
    """A filter on the gene entity, which narrows the genes a step holds."""
    return EdaStringSetFilter(
        entity_id=COUNTS_ENTITY,
        variable_id=GENE_ID_VARIABLE,
        string_set=["PF3D7_0100100"],
    )


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


@dataclass(frozen=True)
class CountedSubset:
    """The dataset, the entity and the filters one gene count was taken over."""

    dataset_id: str
    entity_id: str
    filters: Sequence[EdaFilter]


def wire_gene_count(
    monkeypatch: pytest.MonkeyPatch, *, count: int = 3984
) -> list[CountedSubset]:
    """The gene count the export clears, and what each count was taken over."""
    counted: list[CountedSubset] = []

    async def _count(
        _site: str, *, dataset_id: str, entity_id: str, filters: Sequence[EdaFilter]
    ) -> SubsetCount:
        counted.append(
            CountedSubset(dataset_id=dataset_id, entity_id=entity_id, filters=filters),
        )
        return SubsetCount(entity_id=entity_id, count=count, unfiltered_count=5399)

    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(gene_subset, "verified_count", _count)
    return counted
