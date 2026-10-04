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
from collections.abc import Sequence
from itertools import combinations

import httpx
from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import Field
from veupathdb import strip_html_tags
from veupathdb.domain.parameters import ParamValue, to_wire, wire_map
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import (
    WDKAnswer,
    WDKRecordInstance,
    WDKSearchConfig,
    get_wdk_client,
)
from veupathdb_mcp.catalog import ParameterInfo, wdk_fetch_at
from veupathdb_mcp.wdk import (
    compute_plan_step_counts,
    extract_pk,
    view_filters_for,
)

from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.services.gene_records.attributes import product_attribute

_CONCURRENCY = 4
_MAX_RECORDS = 50_000
_SAMPLE_UNIQUE = 8


class VariantInput(CamelModel):
    """One variant as a caller names it: a search and its parameter values."""

    label: str
    search_name: str
    parameters: dict[str, ParamValue]


class VariantSpec(VariantInput):
    """One variant to run, under the record type the site lists its search under."""

    record_type: str


class PairwiseOverlap(CamelModel):
    a: str
    b: str
    shared: int
    jaccard: float


class UniqueGene(CamelModel):
    """One gene only this variant returns, with the product its record names."""

    gene_id: str
    product: str | None = None


class VariantResult(CamelModel):
    label: str
    search_name: str
    gene_count: int
    unique_count: int
    sample_unique_genes: list[UniqueGene]
    error: str | None = None
    # The strategy's result with this variant in place of the one step that
    # runs its search; None when no single step runs it.
    result_count: int | None = None
    # The wire value of each parameter whose value differs between the variants.
    differs_by: dict[str, str] = Field(default_factory=dict)


class VariantComparison(CamelModel):
    variants: list[VariantResult]
    overlaps: list[PairwiseOverlap]
    truncated: bool = False
    # The root step each ``result_count`` counts; None when none was counted.
    result_step_id: str | None = None

    def fact(self) -> ComparisonFact:
        """The counts of the variants that ran, as a reply's references name them."""
        return ComparisonFact(
            variants=[
                ComparedVariant(
                    label=v.label,
                    gene_count=v.gene_count,
                    unique_count=v.unique_count,
                    result_count=v.result_count,
                    differs_by=v.differs_by,
                )
                for v in self.variants
                if v.error is None
            ],
            overlaps=[
                SharedGenes(a=o.a, b=o.b, shared=o.shared) for o in self.overlaps
            ],
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


async def run_variant_search(
    site_id: str, spec: VariantSpec, *, attributes: Sequence[str] = ()
) -> WDKAnswer:
    """One variant's answer, capped at ``_MAX_RECORDS`` ids and creating no step.

    A transcript search reports one row per gene, so the cap counts genes.
    """
    client = get_wdk_client(site_id)
    report: JSONObject = {
        "attributes": list(attributes),
        "pagination": {"offset": 0, "numRecords": _MAX_RECORDS},
    }
    return await client.run_search_report(
        spec.record_type,
        spec.search_name,
        WDKSearchConfig(parameters=wire_map(spec.parameters)),
        report_config=report,
        view_filters=view_filters_for(spec.record_type),
    )


def _products(
    records: list[WDKRecordInstance], attribute: str | None
) -> dict[str, str | None]:
    """Each record id with the product its record names, None when unread."""
    return {
        record_id: None
        if attribute is None
        else strip_html_tags(record.attribute_text(attribute)) or None
        for record in records
        if (record_id := extract_pk(record))
    }


async def _run_one(
    site_id: str, spec: VariantSpec, sem: asyncio.Semaphore
) -> tuple[VariantSpec, dict[str, str | None], int, str | None]:
    attribute = product_attribute(spec.record_type)
    try:
        async with sem:
            answer = await run_variant_search(
                site_id, spec, attributes=[] if attribute is None else [attribute]
            )
    except (WDKError, httpx.HTTPError) as exc:
        return spec, {}, 0, str(exc)
    products = _products(answer.records, attribute)
    try:
        total = answer.meta.records_returned()
    except ValueError as exc:
        # A comparison of sizes cannot substitute a number for a missing one.
        return spec, products, 0, str(exc)
    return spec, products, total, None


def _differs_by(specs: list[VariantSpec]) -> list[dict[str, str]]:
    """Each spec's wire value of every parameter whose value differs between
    the specs. A spec that names no value for such a parameter holds no entry."""
    wires = [
        {name: to_wire(value) for name, value in spec.parameters.items()}
        for spec in specs
    ]
    names = dict.fromkeys(name for wire in wires for name in wire)
    differing = [name for name in names if len({wire.get(name) for wire in wires}) > 1]
    return [{name: wire[name] for name in differing if name in wire} for wire in wires]


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
    id_sets = {spec.label: set(found) for spec, found, _, err in runs if err is None}
    truncated = any(total > len(found) for _, found, total, err in runs if err is None)

    variants: list[VariantResult] = []
    for (spec, found, total, err), differs in zip(
        runs, _differs_by(specs), strict=True
    ):
        others: set[str] = set()
        for label, other_ids in id_sets.items():
            if label != spec.label:
                others |= other_ids
        unique = sorted(set(found) - others)
        variants.append(
            VariantResult(
                label=spec.label,
                search_name=spec.search_name,
                gene_count=total,
                unique_count=len(unique),
                sample_unique_genes=[
                    UniqueGene(gene_id=gene_id, product=found[gene_id])
                    for gene_id in unique[:_SAMPLE_UNIQUE]
                ],
                error=err,
                differs_by=differs,
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
