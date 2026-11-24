from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.domain.parameters import (
    SHOWN_CANDIDATES,
    Resolution,
    VocabOption,
    VocabularyEntryError,
    exact_entry,
    exact_or_candidates,
)
from veupathdb_mcp.catalog import (
    NamedVocabulary,
    ResolveContext,
    ordered_by_vocabulary,
)

from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    OrganismValue,
    OrthologValue,
)
from strategist.domain.strategy.organism_phrases import (
    completed_entry,
    entry_holding,
)
from strategist.domain.strategy.organism_picks import OrganismPick

ORGANISM_PARAMETER = "organism"


@dataclass(frozen=True)
class NamedOrganisms:
    constraints: list[Constraint]
    picks: list[OrganismPick]


def _orthologs_named(
    c: Constraint, message: str, vocabulary: Sequence[str], options: list[VocabOption]
) -> Constraint:
    match c.value:
        case OrthologValue(organisms=organisms) as asked:
            entries = [_entry(o, message, vocabulary, options) or o for o in organisms]
            named = asked.model_copy(update={"organisms": entries})
            return c.model_copy(update={"value": named})
        case _:
            return c


def _named(c: Constraint, entry: str) -> Constraint:
    return c.model_copy(
        update={"requested_value": entry, "value": OrganismValue(organism=entry)}
    )


def _entry(
    words: str, message: str, vocabulary: Sequence[str], options: list[VocabOption]
) -> str | None:
    exact = exact_entry(options, words)
    return (
        completed_entry(words, message, vocabulary)
        or (None if exact is None else exact.value)
        or entry_holding(words, message, vocabulary)
    )


async def _offered(
    asked: Sequence[tuple[Constraint, Resolution]],
    options: list[VocabOption],
    about: ResolveContext,
) -> list[OrganismPick]:
    if not asked:
        return []
    ordered = await ordered_by_vocabulary(
        VocabularyEntryError([(ORGANISM_PARAMETER, r) for _, r in asked]),
        {ORGANISM_PARAMETER: NamedVocabulary(display="organism", options=options)},
        about,
    )
    return [
        OrganismPick(
            quote=c.quote or "",
            offered=[o.value for o in r.candidates[:SHOWN_CANDIDATES]],
        )
        for (c, _), (_, r) in zip(asked, ordered.faults, strict=True)
    ]


async def named_organisms(
    site_id: str,
    constraints: Sequence[Constraint],
    message: str,
    vocabulary: Sequence[str],
) -> NamedOrganisms:
    options = [VocabOption(value=entry, display=entry) for entry in vocabulary]
    named: list[Constraint] = []
    asked: list[tuple[Constraint, Resolution]] = []
    for c in constraints:
        if c.kind is ConstraintKind.ORTHOLOG:
            named.append(_orthologs_named(c, message, vocabulary, options))
            continue
        words = c.organism
        if c.kind is not ConstraintKind.ORGANISM or words is None or not vocabulary:
            named.append(c)
            continue
        if not c.quote:
            named.append(c.model_copy(update={"value": None}))
            continue
        entry = _entry(words, message, vocabulary, options)
        if entry is not None:
            named.append(_named(c, entry))
            continue
        named.append(c.model_copy(update={"value": None}))
        asked.append((c, exact_or_candidates(options, words, SHOWN_CANDIDATES)))
    picks = await _offered(
        asked, options, ResolveContext(site_id=site_id, message=message)
    )
    return NamedOrganisms(constraints=named, picks=picks)


__all__ = ["NamedOrganisms", "named_organisms"]
