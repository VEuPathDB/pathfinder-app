"""The strategy and step counts a reply states, held to the counts its steps hold."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pathfinder.ai.lead.reply_claims import counts_named_as

_SENTENCE_END = re.compile(r"[.;!?]+(?=\s|$)|\n+")
# A clause that names the strategy or a step states a count of it.
_ABOUT_THE_STRATEGY = re.compile(r"\b(?:strateg(?:y|ies)|steps?)\b", re.IGNORECASE)
# A count of controls or of sampled genes belongs to the evidence rule.
_EVIDENCE_NOUNS = ("control", "sampled")


def misstated_counts(
    prose: str, *, noun: str, record_type: str, held: Sequence[int]
) -> list[int]:
    """The counts of each clause about the strategy that states no held count.

    A clause that states one held count may also state a count it compares it
    with. A count in the record type's own noun is the unit rule's.
    """
    if not held:
        return []
    stated: list[int] = []
    for clause in _SENTENCE_END.split(prose):
        if _ABOUT_THE_STRATEGY.search(clause) is None:
            continue
        evidence = {
            count
            for word in _EVIDENCE_NOUNS
            for count in counts_named_as(clause, word, instead_of=noun)
        }
        counts = [
            count
            for count in counts_named_as(clause, noun, instead_of=record_type)
            if count not in evidence
        ]
        if not any(count in held for count in counts):
            stated.extend(counts)
    return list(dict.fromkeys(stated))


def misstated_count_message(
    noun: str, stated: Sequence[int], held: Sequence[int]
) -> str:
    """Why a reply that states a count no step of the strategy holds is refused."""
    written = " and ".join(f"{count:,} {noun}s" for count in stated)
    counts = [f"{count:,} {noun}s" for count in dict.fromkeys(held)]
    listed = (
        counts[0] if len(counts) == 1 else f"{', '.join(counts[:-1])} and {counts[-1]}"
    )
    holds = "its step holds" if len(counts) == 1 else "its steps hold"
    return (
        f"Your reply states {written} for the strategy, and no step of it holds "
        f"that count: {holds} {listed}. State the count the site returned for "
        f"the step you name."
    )
