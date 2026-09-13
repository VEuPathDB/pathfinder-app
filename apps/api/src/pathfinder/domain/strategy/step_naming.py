"""The words a step's name carries about the values the step asks for."""

from __future__ import annotations

import re
from collections.abc import Mapping

from veupathdb.domain.parameters import ParamValue, to_wire


def _stated(text: str, wire: str) -> list[str]:
    """Every place these words carry this value, alone and not inside a word."""
    return re.findall(rf"(?<!\w){re.escape(wire)}(?!\w)", text)


def states_the_wire_form(text: str, wire: str) -> bool:
    """Whether these words carry this value, on its own and not inside a word."""
    return bool(_stated(text, wire))


def _moved_values(
    name: str,
    *,
    before: Mapping[str, ParamValue],
    after: Mapping[str, ParamValue],
) -> dict[str, str]:
    """The value each moved parameter leaves behind, by the words it wrote.

    A literal the name carries twice identifies no parameter, and neither does
    one two parameters moved apart, so both are left out.
    """
    found: dict[str, str] = {}
    ambiguous: set[str] = set()
    for parameter, value in after.items():
        held = before.get(parameter)
        if held is None:
            continue
        was, holds = to_wire(held), to_wire(value)
        if not was or was == holds or len(_stated(name, was)) != 1:
            continue
        if found.setdefault(was, holds) != holds:
            ambiguous.add(was)
    return {was: holds for was, holds in found.items() if was not in ambiguous}


def name_restating(
    name: str,
    *,
    before: Mapping[str, ParamValue],
    after: Mapping[str, ParamValue],
) -> str:
    """The name with every value the write moved restated.

    One pass over the name the write found, so a value this rewrite states is
    never read as a value the step held. A name that states no moved value is
    the name it was.
    """
    moved = _moved_values(name, before=before, after=after)
    if not moved:
        return name
    alternatives = "|".join(
        re.escape(was) for was in sorted(moved, key=len, reverse=True)
    )
    return re.sub(
        rf"(?<!\w)({alternatives})(?!\w)", lambda found: moved[found.group()], name
    )
