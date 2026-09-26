"""What an arc copies out of the researcher's own message: a name it gives and
the control lists it pastes. No word of it chooses a route."""

from __future__ import annotations

import re

from assistant_core.models.scripted import current_scope_id, current_user_text

from pathfinder.ai.models.mock.directive import without_tokens
from pathfinder.ai.models.mock.site_values import SiteValues

_CONTROLS = re.compile(r"^(Positive|Negative) controls:\s*(.+)$", re.MULTILINE)
_ID_SEPARATOR = re.compile(r"[\s,]+")


def message() -> str:
    """The turn's message, with its arc token taken out."""
    return without_tokens(current_user_text.get())


def named_after(word: str) -> str | None:
    """The words that follow ``word`` to the end of the message, or None."""
    found = re.search(rf"\b{word}\s+(.+?)[.?!]?\s*$", message())
    return None if found is None else found.group(1)


def pasted_controls() -> tuple[list[str], list[str]] | None:
    """The positive and negative ids the message pastes on two labelled lines."""
    lines = {
        label: [i for i in _ID_SEPARATOR.split(ids.strip()) if i]
        for label, ids in _CONTROLS.findall(message())
    }
    if "Positive" not in lines:
        return None
    return lines["Positive"], lines.get("Negative", [])


def turn_controls() -> tuple[list[str], list[str]]:
    """The controls the message pastes, else a seed control set of the site."""
    pasted = pasted_controls()
    if pasted is not None:
        return pasted
    controls = SiteValues.for_site(current_scope_id.get()).controls
    return controls.positive_ids, controls.negative_ids
