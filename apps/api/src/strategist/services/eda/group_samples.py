from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from assistant_core.platform.logging import get_logger
from pydantic import ValidationError
from veupathdb.domain import entity_by_id, variable_by_id, walk_entities
from veupathdb.eda import (
    EdaDifferentialExpressionConfig,
    EdaFilter,
    EdaStringSetFilter,
    EdaStudyDetail,
    get_eda_client,
)
from veupathdb.errors import VEuPathDBError

from strategist.domain.eda_parts import EdaComparison
from strategist.services.eda.compute import comparison_of

logger = get_logger(__name__)


def _held(labels: Sequence[str], count: int) -> str:
    samples = "sample" if count == 1 else "samples"
    return f"({', '.join(labels)}) holds {count} {samples}"


@dataclass(frozen=True, slots=True)
class GroupSamples:
    group_a: int
    group_b: int
    comparison: EdaComparison

    @property
    def stated(self) -> str:
        return (
            f"In this analysis, group A {_held(self.comparison.group_a, self.group_a)} "
            f"and group B {_held(self.comparison.group_b, self.group_b)}."
        )

    @property
    def has_an_empty_group_or_no_replicate(self) -> bool:
        counts = (self.group_a, self.group_b)
        return min(counts) == 0 or max(counts) <= 1


def _sample_entity_id(
    study: EdaStudyDetail, config: EdaDifferentialExpressionConfig
) -> str | None:
    value_entity = config.value_variable.entity_id
    return next(
        (
            entity.id
            for entity in walk_entities(study.root_entity)
            if any(child.id == value_entity for child in entity.children)
        ),
        None,
    )


def _compares_strings(
    study: EdaStudyDetail, config: EdaDifferentialExpressionConfig
) -> bool:
    spec = config.comparator.variable
    entity = entity_by_id(study.root_entity, spec.entity_id)
    variable = None if entity is None else variable_by_id(entity, spec.variable_id)
    return variable is not None and variable.type == "string"


def _group_filter(
    config: EdaDifferentialExpressionConfig, labels: Sequence[str]
) -> EdaStringSetFilter:
    spec = config.comparator.variable
    return EdaStringSetFilter(
        entity_id=spec.entity_id, variable_id=spec.variable_id, string_set=list(labels)
    )


async def group_samples(
    site_id: str,
    *,
    study: EdaStudyDetail,
    config: EdaDifferentialExpressionConfig,
    filters: Sequence[EdaFilter],
) -> GroupSamples | None:
    sample_entity = _sample_entity_id(study, config)
    if sample_entity is None or not _compares_strings(study, config):
        return None
    comparison = comparison_of(config)
    client = get_eda_client(site_id)
    try:
        counts = [
            await client.count(
                study_id=study.id,
                entity_id=sample_entity,
                filters=[*filters, _group_filter(config, labels)],
            )
            for labels in (comparison.group_a, comparison.group_b)
        ]
    except (VEuPathDBError, httpx.HTTPError, ValidationError) as exc:
        logger.warning("Group samples were not read", failure=type(exc).__name__)
        return None
    return GroupSamples(group_a=counts[0], group_b=counts[1], comparison=comparison)


def too_few_samples(samples: GroupSamples | None, *, method: str) -> ValueError | None:
    if samples is None or method != "DESeq":
        return None
    if not samples.has_an_empty_group_or_no_replicate:
        return None
    return ValueError(
        f"No DESeq job started. {samples.stated} A group with no sample, or two "
        f"groups with no replicate in either, is not sent to DESeq. A repeat of this "
        f"call gets the same answer. Tell the researcher these counts, or widen the "
        f"subset or choose groups that hold more samples."
    )
