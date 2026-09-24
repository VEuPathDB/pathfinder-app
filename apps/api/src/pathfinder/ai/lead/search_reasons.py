"""The reply rule for the steps a turn added: each is named by the search it
runs, and one with a recorded reason is given it beside the name."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.ai.lead.contract_messages import unnamed_search_message
from pathfinder.domain.strategy.step_rationale import names_the_phrase, said_beside
from pathfinder.domain.strategy.step_words import AddedSearch


def unnamed_search(prose: str, added: Sequence[AddedSearch]) -> str | None:
    """Every added search is named, and one with a reason is given it beside the name.

    The reason's term is the anchor: the record says it decides the choice, so a
    paragraph or a list item that holds it beside the name has said why.
    """
    unnamed = [a for a in added if not names_the_phrase(prose, a.search_display_name)]
    unreasoned = [
        a
        for a in added
        if a not in unnamed
        and a.rationale is not None
        and not said_beside(prose, a.search_display_name, a.rationale.term)
    ]
    if not unnamed and not unreasoned:
        return None
    return unnamed_search_message(unnamed, unreasoned)
