from __future__ import annotations

from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator
from veupathdb.model import CamelModel

GenomeReading = Literal["at_least_one", "all"]

INCLUDED_SPECIES = "included_species"
PROFILE_PATTERN = "profile_pattern"
MIN_GROUP_GENOMES = 2


def without_stop(text: str) -> str:
    return text.rstrip().rstrip(".").rstrip()


class UnnamedGenomeGroupError(ValueError):
    pass


def genome_words(reading: GenomeReading, name: str) -> str:
    if reading == "at_least_one":
        return f"at least one of the {name}"
    return f"all {name}"


class GenomeGroup(CamelModel):
    model_config = ConfigDict(frozen=True)

    reading: GenomeReading
    genomes: tuple[str, ...] = Field(min_length=MIN_GROUP_GENOMES)
    name: str = ""

    @model_validator(mode="after")
    def _named_with_its_size(self) -> Self:
        if self.name and not self.name.startswith(f"{len(self.genomes):,} "):
            msg = f"{self.name!r} does not name {len(self.genomes)} genomes"
            raise ValueError(msg)
        return self

    @property
    def named(self) -> bool:
        return bool(self.name)

    @property
    def _shown_name(self) -> str:
        if not self.named:
            msg = f"the group of {len(self.genomes)} genomes has no name to show"
            raise UnnamedGenomeGroupError(msg)
        return self.name

    def named_as(self, name: str) -> GenomeGroup:
        return GenomeGroup(reading=self.reading, genomes=self.genomes, name=name)

    @property
    def at_least_one(self) -> bool:
        return self.reading == "at_least_one"

    @property
    def built_words(self) -> str:
        return genome_words(self.reading, self._shown_name)

    @property
    def other_words(self) -> str:
        other: GenomeReading = "all" if self.at_least_one else "at_least_one"
        return genome_words(other, self._shown_name)

    @property
    def _clause(self) -> str:
        return f"; an ortholog in {self.built_words}"

    def unstated_in(self, text: str) -> str:
        if not self.named:
            return text
        stem = without_stop(text)
        return stem.removesuffix(self._clause) if stem.endswith(self._clause) else text

    def stated_in(self, text: str) -> str:
        return f"{without_stop(self.unstated_in(text))}{self._clause}"

    def absent_in(self, text: str) -> str:
        stem = without_stop(self.unstated_in(text))
        return f"{stem}; no ortholog in any of the {self._shown_name}"
