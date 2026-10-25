"""A word for none written just before a reference that renders a count of 0."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from pathfinder.domain.reference_grammar import A_REFERENCE, carries_its_noun

_NONE_WORDS = frozenset({"empty", "zero", "no", "none"})
_LAST_WORD = re.compile(r"([A-Za-z]+)[ \t]*$")


def words_for_none(
    prose: str, rendered: Callable[[re.Match[str]], str | None]
) -> Iterator[tuple[str, str]]:
    for match in A_REFERENCE.finditer(prose):
        shown = rendered(match) if carries_its_noun(match) else None
        if shown is None or shown.split(" ", 1)[0] != "0":
            continue
        before = _LAST_WORD.search(prose, 0, match.start())
        if before is not None and before.group(1).casefold() in _NONE_WORDS:
            yield f"{before.group(1)} {match.group()}", match.group()


__all__ = ["words_for_none"]
