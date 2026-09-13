"""The species a site covers, grouped from the organism vocabulary it declares."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from assistant_core.platform.pydantic_base import CamelModel

# A term reads "Genus species strain": two words name the species, the rest one
# strain of it. An unclassified organism has no species and the whole term names
# it; the catalog marks one with an epithet below or a "-like" suffix on it.
_SPECIES_WORDS = 2
_UNKNOWN_EPITHETS = frozenset({"sp.", "spp.", "cf."})
_UNKNOWN_SUFFIX = "-like"
_EXAMPLE_STRAINS = 3
MAX_SPECIES = 25


class OrganismSummary(CamelModel):
    """One species a site carries, with the strains it lists under it."""

    species: str
    strain_count: int
    strains: list[str]


def _names_no_species(epithet: str) -> bool:
    """Whether this epithet leaves the organism unclassified."""
    lowered = epithet.lower()
    return lowered in _UNKNOWN_EPITHETS or lowered.endswith(_UNKNOWN_SUFFIX)


def _species_and_strain(term: str) -> tuple[str, str]:
    """The species this term belongs to, and the strain it names under it."""
    words = term.split()
    if len(words) <= _SPECIES_WORDS or _names_no_species(words[1]):
        return term, ""
    return " ".join(words[:_SPECIES_WORDS]), " ".join(words[_SPECIES_WORDS:])


def organisms_of_genus(terms: Iterable[str], genus: str) -> list[str]:
    """The terms of one genus, or every term when no genus is named."""
    wanted = genus.strip().lower()
    if not wanted:
        return list(terms)
    return [term for term in terms if term.split()[:1] == [wanted.title()]]


def organism_summaries(terms: Iterable[str]) -> list[OrganismSummary]:
    """The species of a site's organism vocabulary, the widest first."""
    grouped: dict[str, list[str]] = {}
    for term in terms:
        species, strain = _species_and_strain(term)
        strains = grouped.setdefault(species, [])
        if strain:
            strains.append(strain)
    summaries = [
        OrganismSummary(
            species=species,
            strain_count=len(strains),
            strains=strains[:_EXAMPLE_STRAINS],
        )
        for species, strains in grouped.items()
    ]
    return sorted(summaries, key=lambda one: (-one.strain_count, one.species))


def organism_note(omitted: Sequence[str], genus: str) -> str:
    """What the listing left out, and how to reach it.

    A listing of the whole site narrows by genus; one already narrowed to a
    genus names the species it left out instead.
    """
    if not omitted:
        return ""
    if genus:
        return f"{len(omitted)} more species of {genus} are not listed: {', '.join(omitted)}."
    return (
        f"{len(omitted)} more species are not listed. Call describe_site again with "
        f"the genus you want, and it answers with that genus alone."
    )


__all__ = [
    "MAX_SPECIES",
    "OrganismSummary",
    "organism_note",
    "organism_summaries",
    "organisms_of_genus",
]
