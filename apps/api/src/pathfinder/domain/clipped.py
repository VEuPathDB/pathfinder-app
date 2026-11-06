from __future__ import annotations

import re

from pydantic import AfterValidator

_SENTENCE_END = re.compile(r"[.?!](?=\s)")
_LAST_GAP = re.compile(r"\s(?=\S*\Z)")
_ELLIPSIS = "..."


def clipped_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    ends = [m.end() for m in _SENTENCE_END.finditer(text, 0, limit + 1)]
    if ends:
        return text[: ends[-1]]
    room = max(limit - len(_ELLIPSIS), 0)
    gap = _LAST_GAP.search(text, 0, room + 1)
    words = "" if gap is None else text[: gap.start()].rstrip()
    return f"{words or text[:room]}{_ELLIPSIS}"


def text_clipped_to(limit: int) -> AfterValidator:
    def clip(text: str) -> str:
        return clipped_text(text, limit)

    return AfterValidator(clip)


def list_clipped_to(limit: int) -> AfterValidator:
    def clip[T](items: list[T]) -> list[T]:
        return items[:limit]

    return AfterValidator(clip)


def number_at_least(floor: int) -> AfterValidator:
    def clip(number: int) -> int:
        return max(number, floor)

    return AfterValidator(clip)
