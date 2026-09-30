"""The identifiers a scratchpad note carries, which a rewrite of the note must keep."""

from __future__ import annotations

import re

_LOCUS_TAG = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]{1,9}_(?:[A-Z]{0,3}[0-9]{2,}_)?[A-Z]{0,3}[0-9]{3,}[A-Z]?(?:_[A-Z])?\b"
)
_DOTTED_GENE = re.compile(r"\b[A-Z][A-Za-z]{0,5}[0-9]*\.[0-9]+\.[0-9]+\b")
_PREFIXED_GENE = re.compile(r"\b[A-Z]{4}[0-9]{6}\b")
_GRAPH_STEP = re.compile(r"\bstep_[0-9a-f]{8}\b")
_SEARCH_NAME = re.compile(r"\b[A-Z][a-z]+(?:By|With|From)[A-Z][A-Za-z0-9_]*")
# A count stands alone: no letter, digit, dot, colon or hyphen touches its front,
# and it is not the integer part of a decimal.
_COUNT = re.compile(
    r"(?<![A-Za-z0-9_.:,\-])(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})(?![A-Za-z0-9_]|[.,][0-9])"
)
_IDENTIFIERS = (_LOCUS_TAG, _DOTTED_GENE, _PREFIXED_GENE, _GRAPH_STEP, _SEARCH_NAME)


def hard_facts(text: str) -> frozenset[str]:
    """Gene ids, step ids, search names and counts of three or more digits in ``text``.

    A count loses its thousands separators, so ``20,846`` and ``20846`` are one fact.
    """
    facts = {match for pattern in _IDENTIFIERS for match in pattern.findall(text)}
    facts.update(count.replace(",", "") for count in _COUNT.findall(text))
    return frozenset(facts)
