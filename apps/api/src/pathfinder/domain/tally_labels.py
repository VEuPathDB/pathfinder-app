"""The words of the tally rows a reply cites, held in the clause that cites them."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    TALLY_VALUES,
    reference_kind,
)
from pathfinder.domain.reference_placement import clause_texts
from pathfinder.domain.reply_suggestions import token_words
from pathfinder.domain.tally_facts import TallyFact


def cited_row_labels(prose: str, tallies: Sequence[TallyFact]) -> list[str]:
    by_id = {t.id: t for t in tallies}
    labels: list[str] = []
    for match in A_REFERENCE.finditer(prose):
        body = match.group("body") or ""
        if reference_kind(match) != "tally" or body.endswith(TALLY_VALUES):
            continue
        held_id, _, value = body.partition(".")
        tally = by_id.get(held_id)
        rows = [] if tally is None else tally.rows
        labels.extend(r.label for r in rows if r.value == value and r.label)
    return labels


def held_label_words(prose: str, tallies: Sequence[TallyFact]) -> set[str]:
    clauses: list[tuple[set[str], set[str]]] = []
    following: set[str] = set()
    for text in reversed(clause_texts(prose)):
        cited = {
            w for label in cited_row_labels(text, tallies) for w in token_words(label)
        }
        following = cited or following
        clauses.append((token_words(text), following))
    held = {w for words, labelled in clauses for w in words & labelled}
    return held - {w for words, labelled in clauses for w in words - labelled}


__all__ = ["cited_row_labels", "held_label_words"]
