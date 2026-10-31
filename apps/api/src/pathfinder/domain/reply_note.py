from __future__ import annotations

import html
import re

from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.domain.written_links import plain_markdown

A_RECORD = re.compile(r"(?P<gap>[ \t]*)\[record:(?P<record_id>[^\[\]\s]+)\]")
_A_RECORD_LINK = re.compile(r"\[(?P<record_id>[^\[\]\s]+)\]\([^()\s]+\)")


def render_note(note: str, facts: TurnFacts) -> str:
    links = {s.record_id: s.url for s in reversed(facts.citable_records())}
    text = html.unescape(note)
    shown: list[str] = []
    start = 0
    for match in A_RECORD.finditer(text):
        shown.append(plain_markdown(text[start : match.start()]))
        url = links.get(match.group("record_id"))
        if url is not None:
            shown.append(f"{match.group('gap')}[{match.group('record_id')}]({url})")
        start = match.end()
    shown.append(plain_markdown(text[start:]))
    return "".join(shown)


def linked_records(rendered: str) -> list[str]:
    found = (m.group("record_id") for m in _A_RECORD_LINK.finditer(rendered))
    return list(dict.fromkeys(found))


__all__ = [
    "A_RECORD",
    "linked_records",
    "render_note",
]
