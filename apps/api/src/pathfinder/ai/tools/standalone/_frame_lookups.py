"""A typeahead pick binds only an entry a lookup of its parameter reached."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKSearch

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.services.strategies.value_labels import pick_terms

# WDK draws a vocabulary it means to be searched as a type-ahead box.
_TYPEAHEAD = "typeAhead"


def _written_out(term: str, messages: Sequence[str]) -> bool:
    """Whether a message writes the entry as a whole token."""
    token = re.compile(rf"(?<![\w]){re.escape(term)}(?![\w])", re.IGNORECASE)
    return any(token.search(text) for text in messages)


def refuse_a_pick_no_lookup_read(
    state: AgentToolState, definition: WDKSearch, call: CriterionCall
) -> None:
    """Refuse a new entry on a typeahead multi-pick parameter that no lookup
    of that parameter read this pass.

    An entry the criterion already binds, or one the request writes out, is
    not a new pick from a list.
    """
    held = next(
        (
            c.resolved_params
            for c in state.operational_spec_draft.criteria
            if (c.id, c.search_name) == (call.criterion_id, call.search_name)
        ),
        {},
    )
    for param in definition.parameters or []:
        if (
            param.type != "multi-pick-vocabulary"
            or param.display_type != _TYPEAHEAD
            or (call.search_name, param.name) in state.looked_up
        ):
            continue
        kept = pick_terms(held[param.name].value) if param.name in held else []
        new = [
            term
            for term in proposal_values(call.params.get(param.name))
            if term not in kept and not _written_out(term, state.request_messages)
        ]
        if new:
            msg = (
                f"{param.name} ({param.display_name}) on {call.search_name} holds "
                f"{new}, and no lookup of it ran this pass. Read the options for "
                f"{call.text!r} first, then bind the entries a phrase matched: "
                f"get_parameter_options(search_name='{call.search_name}', "
                f"parameter_id='{param.name}', query=[every phrasing of the "
                f"concept, its synonyms and the family names that say it "
                f"another way])."
            )
            raise ModelRetry(msg)
