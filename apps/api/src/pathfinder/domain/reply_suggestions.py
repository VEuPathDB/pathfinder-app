from __future__ import annotations

import re
from collections.abc import Iterator
from itertools import combinations

from pathfinder.domain.scratchpad_facts import hard_facts
from pathfinder.domain.statistic_facts import statistic_references
from pathfinder.domain.tally_facts import tally_references
from pathfinder.domain.turn_facts import ParameterFact, TurnFacts

A_TOKEN = re.compile(r"[\w:./,%+-]+")
EDGE_MARKS = ".,:;/+-_"
_A_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
# The protein-domain and Ensembl accessions a record carries.
_AN_ACCESSION = re.compile(r"PF\d{5}|IPR\d{6}|ENS[A-Z]*[GTP]\d{11}")


def last_change(facts: TurnFacts, side: str) -> int | None:
    return None if facts.last_change is None else facts.last_change.count(side)


def _count_references(facts: TurnFacts) -> Iterator[tuple[str, int]]:
    """Each reference to a count the facts hold, with its count."""
    for step in facts.steps:
        if step.count is not None:
            yield step.step_id, step.count
        if step.count_before is not None:
            yield f"before:{step.step_id}", step.count_before
    for name, count in (
        ("root", facts.root_count),
        ("root_before", facts.root_count_before),
        ("last_change:before", last_change(facts, "before")),
        ("last_change:after", last_change(facts, "after")),
    ):
        if count is not None:
            yield name, count
    for comparison in facts.comparisons:
        for v in comparison.variants:
            yield f"compare:{v.label}", v.gene_count
            yield f"compare:{v.label}:unique", v.unique_count
            if v.result_count is not None:
                yield f"compare:{v.label}:result", v.result_count


def _shown(side: str) -> str:
    """A count side as a reference of its own."""
    if side in ("root", "root_before") or side.startswith(
        ("before:", "compare:", "last_change:")
    ):
        return f"[{side}]"
    return f"[count:{side}]"


def number_references(facts: TurnFacts, number: str) -> tuple[str, ...]:
    """The references that render the number: a count, a difference of two
    counts, the genes two variants share, a value, or a statistic."""
    counts = list(_count_references(facts))
    held = [_shown(side) for side, n in counts if str(n) == number]
    held.extend(
        f"[diff:{a},{b}]"
        for (a, n), (b, m) in combinations(counts, 2)
        if str(abs(n - m)) == number
    )
    held.extend(
        f"[compare:{o.a},{o.b}:shared]"
        for c in facts.comparisons
        for o in c.overlaps
        if str(o.shared) == number
    )
    held.extend(
        f"[value:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if p.value == number
    )
    held.extend(statistic_references(facts.cited_statistics(), number))
    held.extend(tally_references(facts.tallies, number))
    return tuple(dict.fromkeys(held))


def record_references(facts: TurnFacts, token: str) -> tuple[str, ...]:
    ids = {s.record_id for s in facts.citable_records()}
    return (f"[record:{token}]",) if token in ids else ()


def link_references(facts: TurnFacts, link: str) -> tuple[str, ...]:
    if link == facts.strategy_url():
        return ("[url]",)
    return tuple(
        dict.fromkeys(
            f"[record:{s.record_id}]" for s in facts.citable_records() if s.url == link
        )
    )


def an_identifier(token: str) -> bool:
    """A site's gene id, a domain or Ensembl accession, a search name, or a
    snake_case, colon-joined or uuid token. A count is never an identifier."""
    named = any(c.isalpha() for c in token) and token in hard_facts(token)
    shaped = "_" in token or ":" in token or named
    accession = _AN_ACCESSION.fullmatch(token) or _A_UUID.fullmatch(token)
    return shaped or accession is not None


def _holds_the_word(parameter: ParameterFact, token: str) -> bool:
    return token in parameter.value.split() or token in parameter.label.split()


def value_word_references(facts: TurnFacts, token: str) -> tuple[str, ...]:
    """The value references of one value whose value or label holds the token
    as a word."""
    return tuple(
        f"[value:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if p.picks <= 1 and _holds_the_word(p, token)
    )


def listed_value_references(facts: TurnFacts, token: str) -> tuple[str, ...]:
    return tuple(
        f"[value:{step.step_id}.{p.name}]"
        for step in facts.steps
        for p in step.parameters
        if p.picks > 1 and _holds_the_word(p, token)
    )


def product_of(facts: TurnFacts, token: str) -> str:
    """The id of a record whose product holds the number as a word, or ""."""
    return next(
        (
            s.record_id
            for s in facts.citable_records()
            if token in (w.strip(EDGE_MARKS) for w in A_TOKEN.findall(s.product))
        ),
        "",
    )


__all__ = [
    "A_TOKEN",
    "EDGE_MARKS",
    "an_identifier",
    "last_change",
    "link_references",
    "listed_value_references",
    "number_references",
    "product_of",
    "record_references",
    "value_word_references",
]
