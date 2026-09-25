"""The analyses, bindings and commit stand-ins the export cases share.

Each analysis names the dataset of the recorded study it filters, and each gene
count is the distinct gene ids that study answers under the named subset.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaFilter,
    EdaLabeledRange,
    EdaNumberRangeFilter,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaSubsetDescriptor,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)
from veupathdb.testing.eda_fixtures import recorded_distribution

from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.eda import gene_subset
from pathfinder.services.eda.gene_subset import GeneCount
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    phenotype_study,
)
from pathfinder.tests._support.eda_wire import (
    DE_STUDY,
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    fixture,
    gene_id_distribution,
)

WDK_STRATEGY_ID = 330423363

# The recorded RNA-Seq study: twelve samples, and the per-sample counts entity
# that carries the gene id, so each of its rows is one gene in one sample.
DE_DATASET = "DS_e973eadd57"
SAMPLE_ENTITY = "ENT_8151325d"
COUNTS_ENTITY = "ENT_fd574cd6"
TEMPERATURE_VARIABLE = "VAR_081ab087"
_SENSE_COUNT_VARIABLE = "SEQUENCE_READ_COUNT_SENSE"
_GENE_ID_VARIABLE = "VEUPATHDB_GENE_ID"


def _recorded_genes(study_fixture: str) -> GeneCount:
    """The distinct gene ids the site answered under the study's example subset."""
    filtered, whole = (
        recorded_distribution(
            gene_id_distribution(study_fixture, filtered=subset)
        ).statistics
        for subset in (True, False)
    )
    return GeneCount(
        count=filtered.num_distinct_values,
        unfiltered_count=whole.num_distinct_values,
    )


PHENOTYPE_GENES = _recorded_genes("study_detail_phenotype")
DE_GENES = _recorded_genes("study_detail_de")

# One sample filter and no computation, as the researcher reads the refusal.
SAMPLE_ONLY_REFUSAL = (
    "The analysis holds 1 filter on Sample and 0 comparisons, and no filter "
    "on pfal3D7 htseq counts. A step holds genes, and a subset of another "
    "entity selects no genes, so nothing was written. Run a differential "
    "expression comparison and export the genes that pass its cut, or add a "
    "filter on pfal3D7 htseq counts."
)

# The same facts as the model reads them, with the tools that change them.
SAMPLE_ONLY_RETRY = (
    "The analysis holds 1 filter on Sample and 0 comparisons, and no filter "
    "on pfal3D7 htseq counts. A step holds genes, and a subset of another "
    "entity selects no genes, so nothing was written. The gene entity is "
    "pfal3D7 htseq counts (ENT_fd574cd6). Call run_eda_compute to run the "
    "comparison and export the genes that pass its thresholds, or call "
    "set_eda_filters with a filter on pfal3D7 htseq counts."
)

Commit = Callable[..., Awaitable[CommitResult]]


def binding_of(detail: EdaAnalysisDetail) -> ConversationAnalysisView:
    """The binding of one analysis, on the dataset that analysis names."""
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=detail.study_id,
        analysis_id=detail.analysis_id,
        revision=1,
    )


def phenotype_subset() -> EdaAnalysisDetail:
    """The phenotype study's berghei rows, a filter on its gene entity."""
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="berghei subset",
        study_id=PHENOTYPE_DATASET,
        num_filters=1,
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
        ),
    )


def _computation(
    group_a: Sequence[str],
    group_b: Sequence[str],
    volcano: EdaVolcanoConfiguration | None,
) -> EdaComputation:
    return EdaComputation(
        computation_id="c1",
        visualizations=(
            []
            if volcano is None
            else [
                EdaVisualization(
                    visualization_id="v1",
                    descriptor=EdaVolcanoDescriptor(configuration=volcano),
                )
            ]
        ),
        descriptor=EdaDifferentialExpressionDescriptor(
            configuration=EdaDifferentialExpressionConfig(
                identifier_variable=EdaVariableSpec(
                    entity_id=COUNTS_ENTITY, variable_id=_GENE_ID_VARIABLE
                ),
                value_variable=EdaVariableSpec(
                    entity_id=COUNTS_ENTITY, variable_id=_SENSE_COUNT_VARIABLE
                ),
                comparator=EdaComparator(
                    variable=EdaVariableSpec(
                        entity_id=SAMPLE_ENTITY, variable_id=TEMPERATURE_VARIABLE
                    ),
                    group_a=[EdaLabeledRange(label=label) for label in group_a],
                    group_b=[EdaLabeledRange(label=label) for label in group_b],
                ),
            )
        ),
    )


def de_analysis(
    *,
    filters: Sequence[EdaFilter],
    with_computation: bool = False,
    group_a: Sequence[str] = ("febrile",),
    group_b: Sequence[str] = ("normal",),
    volcano: EdaVolcanoConfiguration | None = None,
) -> EdaAnalysisDetail:
    """An analysis of the RNA-Seq study, with its comparison and the volcano cut
    it stores when it holds them."""
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS_ID,
        display_name="heat shock subset",
        study_id=DE_DATASET,
        num_filters=len(filters),
        num_computations=int(with_computation),
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=list(filters)),
            computations=(
                [_computation(group_a, group_b, volcano)] if with_computation else []
            ),
        ),
    )


async def bound(_ctx: object) -> ConversationAnalysisView:
    return binding_of(phenotype_subset())


async def unbound(_ctx: object) -> ConversationAnalysisView | None:
    return None


async def read_detail(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
    assert analysis_id == ANALYSIS_ID
    return phenotype_subset()


def wire_analysis(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, detail: EdaAnalysisDetail
) -> None:
    """Bind ``detail`` to the thread on its own dataset, and read it back."""

    async def bound_to(_ctx: object) -> ConversationAnalysisView:
        return binding_of(detail)

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        assert analysis_id == detail.analysis_id
        return detail

    monkeypatch.setattr(module, "bound_analysis", bound_to)
    monkeypatch.setattr(module, "read_analysis", read)


# The account's permission on the RNA-Seq study, as ``/permissions`` sends it.
DE_PERMISSION = {
    "studyId": DE_STUDY,
    "displayName": "Heat shock response in sensitive mutants (LRR5, DHC)",
    "actionAuthorization": {
        "studyMetadata": True,
        "subsetting": True,
        "resultsAll": True,
    },
}


async def de_study(
    _site: str, dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    """The recorded RNA-Seq study, as the catalog resolves its dataset id."""
    assert dataset_id == DE_DATASET
    detail = EdaStudyDetailResponse.model_validate(fixture("study_detail_de")).study
    return EdaPermissionEntry.model_validate(DE_PERMISSION), detail


def sample_filter() -> EdaStringSetFilter:
    """The six febrile samples, a filter that selects samples and no gene."""
    return EdaStringSetFilter(
        entity_id=SAMPLE_ENTITY,
        variable_id=TEMPERATURE_VARIABLE,
        string_set=["febrile"],
    )


def gene_filter() -> EdaNumberRangeFilter:
    """Counts rows with at least 1000 sense reads, a filter on the gene entity."""
    return EdaNumberRangeFilter(
        entity_id=COUNTS_ENTITY,
        variable_id=_SENSE_COUNT_VARIABLE,
        min=1000,
        max=61892,
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
    """The study, the entity and the filters one gene count was taken over."""

    study_id: str
    entity_id: str
    filters: Sequence[EdaFilter]


StudyReader = Callable[[str, str], Awaitable[tuple[EdaPermissionEntry, EdaStudyDetail]]]


def wire_gene_count(
    monkeypatch: pytest.MonkeyPatch,
    *,
    study: StudyReader = phenotype_study,
    genes: GeneCount = PHENOTYPE_GENES,
) -> list[CountedSubset]:
    """The study the export checks, its gene count, and what each count read."""
    counted: list[CountedSubset] = []

    async def _count(
        _site: str,
        *,
        study: EdaStudyDetail,
        entity_id: str,
        filters: Sequence[EdaFilter],
    ) -> GeneCount:
        counted.append(
            CountedSubset(study_id=study.id, entity_id=entity_id, filters=filters),
        )
        return genes

    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", study)
    monkeypatch.setattr(gene_subset, "gene_count", _count)
    return counted
