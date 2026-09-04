"""Authoring an EDA analysis, and the one place its spec becomes a string."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from assistant_core.platform.types import JSONArray

from pathfinder.domain.eda import validate_filters
from pathfinder.domain.eda_compute_config import validate_compute_config
from pathfinder.domain.eda_filter_checks import DeclaredRanges
from pathfinder.domain.eda_parts import EdaDistributionSeries, EdaEntityCount
from pathfinder.domain.eda_study import entity_by_id, walk_entities
from pathfinder.integrations.eda.factory import (
    get_eda_analyses_client,
    get_eda_client,
)
from pathfinder.integrations.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaBinSpec,
    EdaCategoryVariable,
    EdaComputation,
    EdaDistributionResponse,
    EdaEntity,
    EdaFilter,
    EdaIntegerVariable,
    EdaNewAnalysis,
    EdaNumberDistributionDefaults,
    EdaNumberVariable,
    EdaStudyDetail,
    EdaSubsetDescriptor,
)
from pathfinder.integrations.veupathdb.factory import get_wdk_client
from pathfinder.platform.errors import ValidationError
from pathfinder.services.eda.catalog import (
    get_study_detail_for_dataset,
    resolve_dataset,
    unfiltered_entity_count,
)
from pathfinder.services.eda.description import variable_at

_CONTINUOUS = "continuous"


def new_analysis(
    *,
    dataset_id: str,
    display_name: str,
    filters: Sequence[EdaFilter] = (),
    computation: EdaComputation | None = None,
) -> EdaNewAnalysis:
    """Build the analysis document. ``dataset_id`` lands in the misnamed field."""
    return EdaNewAnalysis(
        study_id=dataset_id,
        display_name=display_name,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=list(filters)),
            computations=[computation] if computation is not None else [],
        ),
    )


def serialize_spec(analysis: EdaNewAnalysis) -> str:
    """The ``eda_analysis_spec`` parameter value for this analysis.

    An analysis with no filters and no computation serializes to the empty
    string: the plugin synthesizes a full empty descriptor, and the literal
    ``{}`` is not what it expects.
    """
    descriptor = analysis.descriptor
    if not descriptor.subset.descriptor and not descriptor.computations:
        return ""
    return analysis.model_dump_json(by_alias=True, exclude_none=True)


@dataclass(frozen=True, slots=True)
class SubsetPreview:
    """A subset's size against the study's, plus one variable's distribution."""

    entity_id: str
    entity_display_name: str
    count: int
    unfiltered_count: int
    distribution: EdaDistributionResponse | None
    distribution_note: str | None = None


@dataclass(frozen=True, slots=True)
class _BinPlan:
    """How to ask for a variable's distribution, or why the ask is skipped."""

    bin_spec: EdaBinSpec | None = None
    skipped: str | None = None


def declared_ranges(study: EdaStudyDetail) -> DeclaredRanges:
    """The numeric bounds the study declares, keyed by (entity, variable)."""
    ranges: dict[tuple[str, str], tuple[float, float]] = {}
    for entity in walk_entities(study.root_entity):
        for variable in entity.variables:
            match variable:
                case EdaNumberVariable() | EdaIntegerVariable():
                    low = variable.distribution_defaults.range_min
                    high = variable.distribution_defaults.range_max
                    if low is not None and high is not None:
                        ranges[(entity.id, variable.id)] = (low, high)
                case _:
                    continue
    return ranges


def subset_errors(study: EdaStudyDetail, filters: Sequence[EdaFilter]) -> list[str]:
    """Every reason this filter array will not mean what it says."""
    return validate_filters(study, list(filters), declared_ranges(study))


@dataclass(frozen=True, slots=True)
class SubsetCount:
    """A subset's size against the entity's whole size."""

    entity_id: str
    count: int
    unfiltered_count: int


def _checked(study: EdaStudyDetail, filters: Sequence[EdaFilter]) -> None:
    """Run the pure predicates. An invalid array never reaches the wire."""
    errors = subset_errors(study, filters)
    if errors:
        raise SubsetRejectedError(errors)


async def verified_count(
    site_id: str,
    *,
    dataset_id: str,
    entity_id: str,
    filters: Sequence[EdaFilter],
) -> SubsetCount:
    """The service's own counts for this subset. Zero is a real answer.

    An out-of-vocabulary value answers 200 with count 0 upstream, so the
    predicates run first and a bad array is refused.
    """
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    _checked(study, filters)
    client = get_eda_client(site_id)
    return SubsetCount(
        entity_id=entity_id,
        count=await client.count(
            study_id=entry.study_id, entity_id=entity_id, filters=filters
        ),
        unfiltered_count=await client.count(
            study_id=entry.study_id, entity_id=entity_id, filters=[]
        ),
    )


async def subset_entity_counts(
    site_id: str,
    *,
    study: EdaStudyDetail,
    filters: Sequence[EdaFilter],
) -> list[EdaEntityCount]:
    """Every entity's subset size against its whole size, in tree order.

    The predicates run once for the array, not once per entity.
    """
    _checked(study, filters)
    client = get_eda_client(site_id)
    return [
        EdaEntityCount(
            entity_id=entity.id,
            entity_display_name=entity.display_name,
            count=await client.count(
                study_id=study.id, entity_id=entity.id, filters=filters
            ),
            unfiltered_count=await unfiltered_entity_count(
                site_id, study_id=study.id, entity_id=entity.id
            ),
        )
        for entity in walk_entities(study.root_entity)
    ]


def _numeric_bin_plan(
    variable_id: str,
    defaults: EdaNumberDistributionDefaults,
) -> _BinPlan:
    if defaults.bin_width is None:
        return _BinPlan(
            skipped=(
                f"Variable {variable_id} is continuous and declares no binWidth, "
                f"so the preview carries no distribution."
            )
        )
    return _BinPlan(
        bin_spec=EdaBinSpec(
            display_range_min=defaults.range_min,
            display_range_max=defaults.range_max,
            bin_width=defaults.bin_width,
        )
    )


def _bin_plan(entity: EdaEntity, variable_id: str) -> _BinPlan:
    """A continuous variable requires a binSpec, and any other refuses one."""
    variable = next((v for v in entity.variables if v.id == variable_id), None)
    match variable:
        case None:
            return _BinPlan(
                skipped=(
                    f"Entity {entity.id} declares no variable {variable_id}, so the "
                    f"preview carries no distribution."
                )
            )
        case EdaCategoryVariable():
            return _BinPlan()
        case EdaNumberVariable() | EdaIntegerVariable() if (
            variable.data_shape == _CONTINUOUS
        ):
            return _numeric_bin_plan(variable.id, variable.distribution_defaults)
        case _ if variable.data_shape == _CONTINUOUS:
            return _BinPlan(
                skipped=(
                    f"Variable {variable.id} is continuous and is not numeric, and "
                    f"the preview builds a numeric binSpec only."
                )
            )
        case _:
            return _BinPlan()


async def preview_subset(
    site_id: str,
    *,
    dataset_id: str,
    entity_id: str,
    filters: Sequence[EdaFilter],
    distribution_variable_id: str | None = None,
) -> SubsetPreview:
    """The filtered and unfiltered counts, and one variable's histogram."""
    entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    _checked(study, filters)
    client = get_eda_client(site_id)
    match entity_by_id(study.root_entity, entity_id):
        case EdaEntity() as entity:
            pass
        case _:
            msg = f"Study {entry.study_id} has no entity {entity_id}."
            raise ValueError(msg)
    filtered = await client.count(
        study_id=entry.study_id, entity_id=entity_id, filters=filters
    )
    unfiltered = await client.count(
        study_id=entry.study_id, entity_id=entity_id, filters=[]
    )
    distribution = None
    note = None
    if distribution_variable_id is not None:
        plan = _bin_plan(entity, distribution_variable_id)
        note = plan.skipped
        if note is None:
            distribution = await client.distribution(
                study_id=entry.study_id,
                entity_id=entity_id,
                variable_id=distribution_variable_id,
                filters=filters,
                bin_spec=plan.bin_spec,
            )
    return SubsetPreview(
        entity_id=entity_id,
        entity_display_name=entity.display_name,
        count=filtered,
        unfiltered_count=unfiltered,
        distribution=distribution,
        distribution_note=note,
    )


def distribution_series(
    distribution: EdaDistributionResponse | None,
    *,
    variable_id: str | None,
    variable_display_name: str,
    is_multi_valued: bool,
) -> EdaDistributionSeries | None:
    """One variable's histogram as both the part and the route carry it."""
    if distribution is None or variable_id is None:
        return None
    statistics = distribution.statistics
    return EdaDistributionSeries(
        variable_id=variable_id,
        variable_display_name=variable_display_name,
        labels=[bin_.bin_label for bin_ in distribution.histogram],
        values=[bin_.value for bin_ in distribution.histogram],
        subset_size=statistics.subset_size,
        num_var_values=statistics.num_var_values,
        num_missing_cases=statistics.num_missing_cases,
        is_multi_valued=is_multi_valued,
    )


async def variable_distribution(
    site_id: str,
    *,
    dataset_id: str,
    entity_id: str,
    variable_id: str,
    filters: Sequence[EdaFilter],
) -> EdaDistributionSeries:
    """One variable's histogram under this subset, as the charts read it."""
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    preview = await preview_subset(
        site_id,
        dataset_id=dataset_id,
        entity_id=entity_id,
        filters=filters,
        distribution_variable_id=variable_id,
    )
    facts = variable_at(study, entity_id, variable_id)
    series = distribution_series(
        preview.distribution,
        variable_id=variable_id,
        variable_display_name="" if facts is None else facts.display_name,
        is_multi_valued=facts is not None and facts.is_multi_valued,
    )
    if series is None:
        raise ValidationError(
            title="No distribution for this variable",
            detail=preview.distribution_note
            or f"Variable {variable_id} carries no distribution on {entity_id}.",
        )
    return series


class SubsetRejectedError(ValidationError):
    """The filter array does not describe the subset it claims to.

    Each message becomes one ``errors`` row, so a surface can show it beside
    the filter that caused it.
    """

    def __init__(self, errors: Sequence[str]) -> None:
        self.messages = list(errors)
        rows: JSONArray = [{"message": message} for message in self.messages]
        super().__init__(
            title="Subset rejected",
            detail=" ".join(self.messages),
            errors=rows,
        )


async def resolve_eda_user_id(site_id: str) -> str:
    """The numeric WDK user id the analysis routes are keyed by."""
    return await get_eda_analyses_client(site_id).resolve_user_id(
        get_wdk_client(site_id)
    )


async def open_analysis(
    site_id: str,
    *,
    dataset_id: str,
    display_name: str,
) -> str:
    """Create the upstream analysis this conversation edits. Returns its id."""
    await resolve_dataset(site_id, dataset_id)
    analyses = get_eda_analyses_client(site_id)
    created = await analyses.create(
        user_id=await resolve_eda_user_id(site_id),
        analysis=new_analysis(dataset_id=dataset_id, display_name=display_name),
    )
    return created.analysis_id


async def patch_subset(
    site_id: str,
    *,
    analysis_id: str,
    dataset_id: str,
    filters: Sequence[EdaFilter],
) -> EdaAnalysisDetail:
    """Replace the analysis's subset. The upstream document stays the SSOT."""
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    _checked(study, filters)
    return await _patch(
        site_id,
        analysis_id=analysis_id,
        mutate=lambda current: current.model_copy(
            update={"subset": EdaSubsetDescriptor(descriptor=list(filters))},
        ),
    )


async def apply_computation(
    site_id: str,
    *,
    analysis_id: str,
    dataset_id: str,
    computation: EdaComputation,
) -> EdaAnalysisDetail:
    """Replace the analysis's single computation, after checking its config."""
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    errors = validate_compute_config(study, computation.descriptor.configuration)
    if errors:
        raise SubsetRejectedError(errors)
    return await _patch(
        site_id,
        analysis_id=analysis_id,
        mutate=lambda current: current.model_copy(
            update={"computations": [computation]},
        ),
    )


async def _patch(
    site_id: str,
    *,
    analysis_id: str,
    mutate: Callable[[EdaAnalysisDescriptor], EdaAnalysisDescriptor],
) -> EdaAnalysisDetail:
    """Read the upstream descriptor, apply one change, write it back, re-read.

    Upstream owns the document, so the read after the write is what both
    surfaces render.
    """
    analyses = get_eda_analyses_client(site_id)
    user_id = await resolve_eda_user_id(site_id)
    current = await analyses.get(user_id=user_id, analysis_id=analysis_id)
    await analyses.patch_descriptor(
        user_id=user_id,
        analysis_id=analysis_id,
        descriptor=mutate(current.descriptor),
    )
    return await analyses.get(user_id=user_id, analysis_id=analysis_id)
