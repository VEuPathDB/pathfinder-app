"""The counts one completed comparison of search variants returned, which a
reply's comparison references render."""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from pathfinder.domain.count_words import counted

# The wire value of a multi-pick parameter: a JSON list of its entries.
_PICKED_ENTRIES: TypeAdapter[list[str]] = TypeAdapter(list[str])


class ComparedVariant(CamelModel):
    """One variant a comparison ran: its genes, the genes no other variant
    returned, the strategy's result with the variant in place, and the wire
    value of each parameter whose value differs between the variants."""

    model_config = ConfigDict(frozen=True)

    label: str
    gene_count: int
    unique_count: int
    result_count: int | None = None
    differs_by: dict[str, str] = Field(default_factory=dict)

    def row(self, noun: str) -> str:
        """The variant's count, after the values it differs by from the others."""
        differs = "; ".join(
            f"{name}: {_shown_value(wire)}" for name, wire in self.differs_by.items()
        )
        searched = f"{self.label} ({differs})" if differs else self.label
        return f"{searched}: {counted(self.gene_count, noun)}"


def _shown_value(wire: str) -> str:
    """A multi-pick wire value as its entries, any other wire value as it is."""
    try:
        return ", ".join(_PICKED_ENTRIES.validate_json(wire))
    except ValidationError:
        return wire


class SharedGenes(CamelModel):
    """The genes two variants of one comparison both returned."""

    model_config = ConfigDict(frozen=True)

    a: str
    b: str
    shared: int


class ComparisonFact(CamelModel):
    """The counts one completed comparison of this turn returned, for the
    variants that ran."""

    model_config = ConfigDict(frozen=True)

    variants: list[ComparedVariant] = Field(default_factory=list)
    overlaps: list[SharedGenes] = Field(default_factory=list)

    def redacted(self, redact: Callable[[str], str]) -> ComparisonFact:
        return self.model_copy(
            update={
                "variants": [
                    v.model_copy(update={"label": redact(v.label)})
                    for v in self.variants
                ],
                "overlaps": [
                    o.model_copy(update={"a": redact(o.a), "b": redact(o.b)})
                    for o in self.overlaps
                ],
            }
        )


__all__ = ["ComparedVariant", "ComparisonFact", "SharedGenes"]
