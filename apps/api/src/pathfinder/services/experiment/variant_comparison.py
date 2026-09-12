"""Exploratory variant comparison — run N search-config variants and compare
their result gene sets WITHOUT control sets or scoring.

This is the conversational, no-controls counterpart to the workbench's
benchmark mode: the user wants to "try both" / sweep a parameter / ablate a
step and SEE how the results differ (sizes, overlap, distinguishing genes),
then judge for themselves. Each variant runs via WDK's anonymous report
endpoint (``run_search_report``) — no step/strategy is created, so the user's
workspace is untouched and variants run in parallel.
"""

from __future__ import annotations

import asyncio
from itertools import combinations

import httpx
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from veupathdb.domain.parameters import ParamValue, wire_map
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKAnswer, WDKSearchConfig, get_wdk_client
from veupathdb_mcp.wdk import extract_record_ids

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


class VariantComparison(CamelModel):
    variants: list[VariantResult]
    overlaps: list[PairwiseOverlap]
    truncated: bool = False


async def run_variant_search(site_id: str, spec: VariantSpec) -> WDKAnswer:
    """One variant's answer, capped at ``_MAX_RECORDS`` ids and creating no step."""
    client = get_wdk_client(site_id)
    return await client.run_search_report(
        spec.record_type,
        spec.search_name,
        WDKSearchConfig(parameters=wire_map(spec.parameters)),
        report_config=_ALL_IDS_REPORT,
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
