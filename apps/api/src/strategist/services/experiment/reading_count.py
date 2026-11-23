from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import Field
from veupathdb import strip_html_tags
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    format_param_info_typed,
    organism_parameter_of,
    read_search_definition,
)

from strategist.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.ranking import gene_scores
from strategist.domain.strategy.reading_plan import (
    combined_ids,
    reading_label,
    reading_roles,
    reading_shape_refusal,
)
from strategist.domain.strategy.value_binding import bind_values
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
    run_variant_search,
)
from strategist.services.strategies.search_sheets import radio_halves


class ReadingTooLargeError(ValueError):
    def __init__(self, label: str, total: int, read: int) -> None:
        self.label = label
        self.total = total
        self.read = read
        super().__init__(
            f"{label} returns {total:,} genes, more than a reading's count reads in "
            f"one read of {read:,} records. Narrow it, for example to one organism."
        )


class ProposedSearch(VariantInput):
    weight: int | None = Field(
        default=None,
        description=(
            "Set on every search of a ranking plan: 1 each, unless the researcher "
            "says one kind of evidence matters more. Leave it out of a filter plan."
        ),
    )


class ProposedReading(CamelModel):
    title: str = Field(
        min_length=3,
        max_length=80,
        description=(
            "A short title of the plan in the researcher's terms. The card and the "
            "Build button show it, and Strategist writes the plan's steps under it."
        ),
    )
    searches: Annotated[
        list[ProposedSearch],
        Field(
            min_length=1,
            description=(
                "Each catalog search of the plan with its parameter values. Its "
                "label is a short id the structure names it by. In a ranking "
                "plan each search carries a weight, and a gene scores the sum of "
                "the weights of the searches that find it."
            ),
        ),
    ]
    structure: StructureNode | None = Field(
        default=None,
        description=(
            "How the searches combine: leaves name a search by its label, and a "
            'combine is {"kind": "combine", "operator": "INTERSECT" | "UNION" | '
            '"MINUS", "inputs": [<left>, <right>]}. Leave it out for one search, '
            "and for a ranking plan, which is the UNION of its searches."
        ),
    )
    also: str = Field(
        default="",
        description=(
            "What Build adds that these searches cannot state, in words: a map to "
            "orthologs, a study analysis, a saved strategy. Empty when the plan is "
            "the searches alone."
        ),
    )

    @property
    def weights(self) -> dict[str, int]:
        return {s.label: s.weight for s in self.searches if s.weight is not None}

    @property
    def root(self) -> StructureNode:
        if self.structure is not None:
            return self.structure
        leaves = [
            StructureNode(kind="leaf", criterion_id=s.label) for s in self.searches
        ]
        if len(leaves) == 1:
            return leaves[0]
        return StructureNode(kind="combine", operator=CombineOp.UNION, inputs=leaves)

    def shape_problems(self) -> list[str]:
        names = [search.label for search in self.searches]
        if len(set(names)) < len(names):
            return [
                f"Each search of a proposal has its own label; these repeat: {names}."
            ]
        if self.structure is None and len(names) > 1 and not self.weights:
            return [
                f"A proposal states how its {len(names)} searches combine in structure."
            ]
        refusal = reading_shape_refusal(self.root, names)
        return [] if refusal is None else [refusal]


class CountedReading(CamelModel):
    label: str
    gene_count: int | None
    spec: OperationalSpec
    not_counted: str = ""
    scores: dict[int, int] = Field(default_factory=dict)


type _RecordKey = tuple[str, ...]


def _genes(keys: frozenset[_RecordKey]) -> set[str]:
    return {key[0] for key in keys if key}


async def _ids(site_id: str, spec: VariantSpec) -> frozenset[_RecordKey]:
    answer = await run_variant_search(site_id, spec, every_transcript=True)
    if len(answer.records) >= variant_comparison.READ_CAP:
        raise ReadingTooLargeError(
            spec.label, answer.meta.records_returned(), variant_comparison.READ_CAP
        )
    return frozenset(
        tuple(part.value for part in record.id) for record in answer.records
    )


def _criterion(
    spec: VariantSpec,
    definition: WDKSearch,
    role: CriterionRole,
    weight: int | None,
    *,
    organism: str | None,
) -> Criterion:
    sheet = [
        info
        for info in format_param_info_typed(
            definition.parameters or [], organism=organism
        )
        if info.bindable
    ]
    return Criterion(
        id=spec.label,
        text=spec.label,
        search_name=spec.search_name,
        search_display_name=strip_html_tags(definition.display_name)
        or definition.url_segment,
        record_class=spec.record_type,
        role=role,
        organism_param=next((i.name for i in sheet if i.organism_param), None),
        radio_pairs=radio_halves(definition),
        resolved_params=bind_values(spec.parameters, "card", sheet),
        confidence=1.0,
        weight=weight,
    )


async def _count(
    site_id: str,
    searches: list[VariantSpec],
    root: StructureNode,
    weights: Mapping[str, int],
) -> tuple[int | None, dict[int, int], str]:
    try:
        ids = {spec.label: await _ids(site_id, spec) for spec in searches}
    except ReadingTooLargeError as too_large:
        return None, {}, str(too_large)
    kept = _genes(combined_ids(root, ids))
    held = {label: _genes(keys) for label, keys in ids.items()}
    scores = gene_scores(held, weights, kept) if weights else {}
    return len(kept), scores, ""


async def count_reading(
    site_id: str,
    searches: list[VariantSpec],
    root: StructureNode,
    weights: Mapping[str, int],
) -> CountedReading:
    roles = reading_roles(root)
    criteria = []
    for search in searches:
        definition = await read_search_definition(
            site_id, search.record_type, search.search_name
        )
        organism = await organism_parameter_of(site_id, definition.parameters or [])
        criteria.append(
            _criterion(
                search,
                definition,
                roles[search.label],
                weights.get(search.label),
                organism=organism,
            )
        )
    spec = OperationalSpec(criteria=criteria, structure=SpecStructure(root=root))
    label = reading_label(spec)
    gene_count, scores, not_counted = await _count(site_id, searches, root, weights)
    return CountedReading(
        label=label,
        gene_count=gene_count,
        spec=spec.model_copy(update={"goal": label}),
        not_counted=not_counted,
        scores=scores,
    )


__all__ = ["CountedReading", "ProposedReading", "ProposedSearch", "count_reading"]
