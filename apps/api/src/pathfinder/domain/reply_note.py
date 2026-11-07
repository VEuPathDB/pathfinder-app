from __future__ import annotations

import re

from pathfinder.domain.turn_facts import TurnFacts

A_RECORD = re.compile(r"(?P<gap>[ \t]*)\[record:(?P<record_id>[^\[\]\s]+)\]")
_A_RECORD_LINK = re.compile(r"(?<!!)\[(?P<record_id>[^\[\]\s]+)\]\([^()\s]+\)")


def render_note(note: str, facts: TurnFacts) -> str:
    links = {s.record_id: s.url for s in reversed(facts.citable_records())}

    def linked(match: re.Match[str]) -> str:
        url = links.get(match.group("record_id"))
        if url is None:
            return ""
        return f"{match.group('gap')}[{match.group('record_id')}]({url})"

    return A_RECORD.sub(linked, note)


def linked_records(rendered: str) -> list[str]:
    found = (m.group("record_id") for m in _A_RECORD_LINK.finditer(rendered))
    return list(dict.fromkeys(found))


__all__ = [
    "A_RECORD",
    "linked_records",
    "render_note",
]
