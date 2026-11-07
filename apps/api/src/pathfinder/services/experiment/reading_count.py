from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator
from veupathdb import strip_html_tags
from veupathdb.model import CamelModel
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import format_param_info_typed, read_search_definition
from veupathdb_mcp.wdk import extract_pk

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.reading_plan import (
    combined_ids,
    reading_label,
    reading_roles,
    reading_shape_refusal,
)
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
    run_variant_search,
)
from pathfinder.services.strategies.search_sheets import radio_halves


class ReadingTooLargeError(ValueError):
    def __init__(self, label: str, total: int, read: int) -> None:
        self.label = label
        self.total = total
        self.read = read
        super().__init__(
            f"{label} returns {total:,} genes, more than the {read:,} a reading's "
            "count reads. Narrow it, for example to one organism."
        )


class ProposedReading(CamelModel):
    searches: Annotated[
        list[VariantInput],
        Field(
            min_length=1,
            description=(
                "Each catalog search of the plan with its parameter values. Its "
                "label is a short id the structure names it by."
            ),
        ),
    ]
    structure: StructureNode | None = Field(
        default=None,
        description=(
            "How the searches combine: leaves name a search by its label, and a "
            'combine is {"kind": "combine", "operator": "INTERSECT" | "UNION" | '
            '"MINUS", "inputs": [<left>, <right>]}. Leave it out for one search.'
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
    def root(self) -> StructureNode:
        if self.structure is not None:
            return self.structure
        return StructureNode(kind="leaf", criterion_id=self.searches[0].label)

    @model_validator(mode="after")
    def _states_a_countable_plan(self) -> Self:
        names = [search.label for search in self.searches]
        if len(set(names)) < len(names):
            msg = f"Each search of a proposal has its own label; these repeat: {names}."
            raise ValueError(msg)
        if self.structure is None and len(names) > 1:
            msg = (
                f"A proposal states how its {len(names)} searches combine in structure."
            )
            raise ValueError(msg)
        refusal = reading_shape_refusal(self.root, names)
        if refusal is not None:
            raise ValueError(refusal)
        return self


class CountedReading(CamelModel):
    label: str
    gene_count: int | None
    spec: OperationalSpec
    not_counted: str = ""


async def _ids(site_id: str, spec: VariantSpec) -> frozenset[str]:
    answer = await run_variant_search(site_id, spec)
    found = frozenset(pk for record in answer.records if (pk := extract_pk(record)))
    total = answer.meta.records_returned()
    if total > len(found):
        raise ReadingTooLargeError(spec.label, total, len(found))
    return found


def _criterion(
    spec: VariantSpec, definition: WDKSearch, role: CriterionRole
) -> Criterion:
    sheet = [
        info
        for info in format_param_info_typed(definition.parameters or [])
        if info.is_visible
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
    )


async def _count(
    site_id: str, searches: list[VariantSpec], root: StructureNode
) -> tuple[int | None, str]:
    try:
        ids = {spec.label: await _ids(site_id, spec) for spec in searches}
    except ReadingTooLargeError as too_large:
        return None, str(too_large)
    return len(combined_ids(root, ids)), ""


async def count_reading(
    site_id: str, searches: list[VariantSpec], root: StructureNode
) -> CountedReading:
    roles = reading_roles(root)
    criteria = [
        _criterion(
            spec,
            await read_search_definition(site_id, spec.record_type, spec.search_name),
            roles[spec.label],
        )
        for spec in searches
    ]
    spec = OperationalSpec(criteria=criteria, structure=SpecStructure(root=root))
    label = reading_label(spec)
    gene_count, not_counted = await _count(site_id, searches, root)
    return CountedReading(
        label=label,
        gene_count=gene_count,
        spec=spec.model_copy(update={"goal": label}),
        not_counted=not_counted,
    )


__all__ = ["CountedReading", "ProposedReading", "count_reading"]
