"""Gene-list extraction and metadata hydration for experiment execution."""

from collections.abc import Awaitable, Callable

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from veupathdb.domain.parameters import ParamValue
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.controls import (
    ControlsContext,
    ControlTestResult,
    IntersectionConfig,
)
from veupathdb_mcp.gene_lookup import GeneResult, resolve_gene_ids

from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.services.experiment.types import ExperimentConfig, GeneInfo

logger = get_logger(__name__)

ProgressCallback = Callable[[JSONObject], Awaitable[None]]
"""Emits one progress event."""


def intersection_config_from_config(
    config: ExperimentConfig,
    *,
    target_parameters: dict[str, ParamValue] | None = None,
) -> IntersectionConfig:
    """Build an intersection config from an experiment config.

    ``target_parameters`` overrides ``config.parameters``.
    """
    return IntersectionConfig(
        site_id=config.site_id,
        record_type=config.record_type,
        target_search_name=config.search_name,
        target_parameters=(
            target_parameters if target_parameters is not None else config.parameters
        ),
        controls_search_name=config.controls_search_name,
        controls_param_name=config.controls_param_name,
        controls_value_format=config.controls_value_format,
        internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
    )


def controls_context_from_config(config: ExperimentConfig) -> ControlsContext:
    """Build a controls context from an experiment config."""
    return ControlsContext(
        site_id=config.site_id,
        record_type=config.record_type,
        controls_search_name=config.controls_search_name,
        controls_param_name=config.controls_param_name,
        controls_value_format=config.controls_value_format,
        positive_controls=config.positive_controls or [],
        negative_controls=config.negative_controls or [],
    )


def _ids_to_gene_infos(ids: list[str] | None) -> list[GeneInfo]:
    """Wrap gene ID strings as gene info objects. A set that read no ids is empty."""
    return [GeneInfo(id=g) for g in ids or ()]


def _hydrate_list(
    genes: list[GeneInfo],
    lookup: dict[str, GeneResult],
) -> list[GeneInfo]:
    """Add name, organism, and product to each gene from the lookup."""
    hydrated: list[GeneInfo] = []
    for g in genes:
        meta = lookup.get(g.id)
        if meta:
            hydrated.append(
                GeneInfo(
                    id=g.id,
                    name=meta.gene_name or g.name,
                    organism=meta.organism or g.organism,
                    product=meta.product or g.product,
                )
            )
        else:
            hydrated.append(g)
    return hydrated


async def _resolve_gene_lookup(
    site_id: str,
    gene_lists: tuple[list[GeneInfo], ...],
) -> dict[str, GeneResult]:
    """Resolve every unique gene ID across the lists into a lookup by gene ID."""
    all_ids: list[str] = []
    seen: set[str] = set()
    for gl in gene_lists:
        for g in gl:
            if g.id not in seen:
                all_ids.append(g.id)
                seen.add(g.id)

    if not all_ids:
        return {}

    resolved = await resolve_gene_ids(site_id=site_id, gene_ids=all_ids)
    if not resolved.records:
        return {}

    lookup: dict[str, GeneResult] = {}
    for rec in resolved.records:
        if rec.gene_id:
            lookup[rec.gene_id] = rec
    return lookup


async def extract_and_hydrate_genes(
    *,
    site_id: str,
    result: ControlTestResult,
    negative_controls: list[str] | None = None,
) -> tuple[list[GeneInfo], list[GeneInfo], list[GeneInfo], list[GeneInfo]]:
    """Extract the four control-test gene lists and add WDK metadata.

    A control set that read no identifiers names no gene in either of its two
    lists. The counts on the result carry that run; a list built without the
    identifiers would contradict them.

    :returns: Tuple of (true positive, false negative, false positive, true negative).
    """
    positive = result.positive
    negative = result.negative
    tp = _ids_to_gene_infos(positive.intersection_ids if positive else None)
    fn = _ids_to_gene_infos(positive.missing_ids_sample if positive else None)
    fp = _ids_to_gene_infos(negative.intersection_ids if negative else None)

    tn = _ids_to_gene_infos(negative.missing_ids_sample if negative else None)
    hits = negative.intersection_ids if negative else None
    if not tn and negative_controls and hits is not None:
        hit_ids = set(hits)
        tn = [GeneInfo(id=g) for g in negative_controls if g not in hit_ids]

    try:
        lookup = await _resolve_gene_lookup(site_id, (tp, fn, fp, tn))
    except VEuPathDBError as exc:
        logger.warning("Gene hydration failed, returning bare IDs", error=str(exc))
        return tp, fn, fp, tn

    if lookup:
        tp = _hydrate_list(tp, lookup)
        fn = _hydrate_list(fn, lookup)
        fp = _hydrate_list(fp, lookup)
        tn = _hydrate_list(tn, lookup)

    return tp, fn, fp, tn
