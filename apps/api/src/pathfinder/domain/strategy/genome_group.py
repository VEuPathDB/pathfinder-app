from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field
from veupathdb.model import CamelModel

GenomeReading = Literal["at_least_one", "all"]

INCLUDED_SPECIES = "included_species"
PROFILE_PATTERN = "profile_pattern"
MIN_GROUP_GENOMES = 2


def genome_words(reading: GenomeReading, count: int) -> str:
    if reading == "at_least_one":
        return f"at least one of {count} genomes"
    return f"all {count} genomes"


class GenomeGroup(CamelModel):
    model_config = ConfigDict(frozen=True)

    reading: GenomeReading
    genomes: tuple[str, ...] = Field(min_length=MIN_GROUP_GENOMES)

    @property
    def at_least_one(self) -> bool:
        return self.reading == "at_least_one"

    @property
    def built_words(self) -> str:
        return genome_words(self.reading, len(self.genomes))

    @property
    def other_words(self) -> str:
        other: GenomeReading = "all" if self.at_least_one else "at_least_one"
        return genome_words(other, len(self.genomes))
