"""Exploratory variant comparison - run N search-config variants and compare
their result gene sets WITHOUT control sets or scoring.

This is the conversational, no-controls counterpart to the scored comparison:
the user wants to "try both" / sweep a parameter / ablate a
step and SEE how the results differ (sizes, overlap, distinguishing genes),
then judge for themselves. Each variant runs via WDK's anonymous report
endpoint (``run_search_report``) - no step/strategy is created, so the user's
workspace is untouched and variants run in parallel.
"""

from __future__ import annotations

import asyncio
from itertools import combinations

import httpx
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from veupathdb.domain.parameters import ParamValue, wire_map
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import WDKAnswer, WDKSearchConfig, get_wdk_client
from veupathdb_mcp.catalog import ParameterInfo, wdk_fetch_at
from veupathdb_mcp.wdk import (
    compute_plan_step_counts,
    extract_record_ids,
    view_filters_for,
)

_CONCURRENCY = 4
_MAX_RECORDS = 50_000
_SAMPLE_UNIQUE = 8

_ALL_IDS_REPORT: JSONObject = {
    "attributes": [],
    "pagination": {"offset": 0, "numRecords": _MAX_RECORDS},
}


class VariantSpec(CamelModel):
    """One variant to run: a search + its parameter values."""

    label: str
    record_type: str = "transcript"
    search_name: str
    parameters: dict[str, ParamValue]


class PairwiseOverlap(CamelModel):
    a: str
    b: str
    shared: int
    jaccard: float


class VariantResult(CamelModel):
    label: str
    search_name: str
    gene_count: int
    unique_count: int
    sample_unique_genes: list[str]
    error: str | None = None
    # The strategy's result with this variant in place of the one step that
    # runs its search; None when no single step runs it.
    result_count: int | None = None


class VariantComparison(CamelModel):
    variants: list[VariantResult]
    overlaps: list[PairwiseOverlap]
    truncated: bool = False
    # The root step each ``result_count`` counts; None when none was counted.
    result_step_id: str | None = None

    def counts(self) -> frozenset[int]:
        """Every count a variant that ran returned: its genes, its result, its
        unique genes, and the genes each pair shares."""
        ran = [v for v in self.variants if v.error is None]
        return frozenset(
            {
                *(v.gene_count for v in ran),
                *(v.unique_count for v in ran),
                *(v.result_count for v in ran if v.result_count is not None),
                *(o.shared for o in self.overlaps),
            }
        )


async def search_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    """The parameters the site's search takes, each with the vocabulary the
    parent values in ``context`` give it."""
    return await wdk_fetch_at(site_id, record_type, search_name)(context)


def _in_place(ast: StrategyAst, step_id: str, spec: VariantSpec) -> StrategyAst:
    """The strategy with the variant's values set on the step that runs its search."""
    placed = ast.model_copy(deep=True)
    node = next(node for node in walk(placed.root) if node.id == step_id)
    node.parameters = {**node.parameters, **spec.parameters}
    return placed


async def _result_count(
    site_id: str, ast: StrategyAst, step_id: str | None, spec: VariantSpec
) -> int | None:
    if step_id is None:
        return None
    try:
        counts = await compute_plan_step_counts(_in_place(ast, step_id, spec), site_id)
    except VEuPathDBError, httpx.HTTPError:
        return None
    return counts.get(ast.root.id)


async def counted_in_place(
    site_id: str,
    comparison: VariantComparison,
    specs: list[VariantSpec],
    *,
    strategy: StrategyAst,
    steps: dict[str, str],
) -> VariantComparison:
    """The comparison with each variant counted at the strategy's result.

    ``steps`` names, by variant label, the one step that runs its search; a
    variant that failed or has no step keeps no result count.
    """
    ran = {v.label for v in comparison.variants if v.error is None}
    counts = await asyncio.gather(
        *(
            _result_count(
                site_id,
                strategy,
                steps.get(spec.label) if spec.label in ran else None,
                spec,
            )
            for spec in specs
        )
    )
    by_label = dict(zip((spec.label for spec in specs), counts, strict=True))
    return comparison.model_copy(
        update={
            "variants": [
                v.model_copy(update={"result_count": by_label.get(v.label)})
                for v in comparison.variants
            ],
            "result_step_id": strategy.root.id
            if any(c is not None for c in counts)
            else None,
        }
    )


async def run_variant_search(site_id: str, spec: VariantSpec) -> WDKAnswer:
    """One variant's answer, capped at ``_MAX_RECORDS`` ids and creating no step.

    A transcript search reports one row per gene, so the cap counts genes.
    """
    client = get_wdk_client(site_id)
    return await client.run_search_report(
        spec.record_type,
        spec.search_name,
        WDKSearchConfig(parameters=wire_map(spec.parameters)),
        report_config=_ALL_IDS_REPORT,
        view_filters=view_filters_for(spec.record_type),
    )


async def _run_one(
    site_id: str, spec: VariantSpec, sem: asyncio.Semaphore
) -> tuple[VariantSpec, set[str], int, str | None]:
    try:
        async with sem:
            answer = await run_variant_search(site_id, spec)
    except (WDKError, httpx.HTTPError) as exc:
        return spec, set(), 0, str(exc)
    ids = set(extract_record_ids(answer.records))
    try:
        total = answer.meta.records_returned()
    except ValueError as exc:
        # A comparison of sizes cannot substitute a number for a missing one.
        return spec, ids, 0, str(exc)
    return spec, ids, total, None


async def run_variant_comparison(
    site_id: str,
    specs: list[VariantSpec],
) -> VariantComparison:
    """Run each variant's search and compare result gene sets.

    ``gene_count`` is the variant's full WDK result count; overlap and
    ``unique_count`` are computed over the retrieved IDs (capped at
    ``_MAX_RECORDS``). ``truncated`` flags when any variant exceeded the cap,
    so overlap figures are lower bounds.
    """
    sem = asyncio.Semaphore(_CONCURRENCY)
    runs = await asyncio.gather(*(_run_one(site_id, s, sem) for s in specs))

    # Only successful variants participate in overlap; errored ones are
    # reported with their message but contribute no gene set.
    id_sets = {spec.label: ids for spec, ids, _, err in runs if err is None}
    truncated = any(total > len(ids) for _, ids, total, err in runs if err is None)

    variants: list[VariantResult] = []
    for spec, ids, total, err in runs:
        others: set[str] = set()
        for label, other_ids in id_sets.items():
            if label != spec.label:
                others |= other_ids
        unique = sorted(ids - others)
        variants.append(
            VariantResult(
                label=spec.label,
                search_name=spec.search_name,
                gene_count=total,
                unique_count=len(unique),
                sample_unique_genes=unique[:_SAMPLE_UNIQUE],
                error=err,
            )
        )

    overlaps: list[PairwiseOverlap] = []
    for (label_a, set_a), (label_b, set_b) in combinations(id_sets.items(), 2):
        shared = set_a & set_b
        union = set_a | set_b
        overlaps.append(
            PairwiseOverlap(
                a=label_a,
                b=label_b,
                shared=len(shared),
                jaccard=round(len(shared) / len(union), 4) if union else 0.0,
            )
        )

    return VariantComparison(variants=variants, overlaps=overlaps, truncated=truncated)
