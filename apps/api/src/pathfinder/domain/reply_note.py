from __future__ import annotations

import re

from pathfinder.domain.list_items import without_item_numbers
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.domain.written_links import without_links, written_links

A_RECORD = re.compile(r"(?P<gap>[ \t]*)\[record:(?P<record_id>[^\[\]\s]+)\]")
_A_TOKEN = re.compile(r"[\w:./,%+-]+")
_EDGE_MARKS = ".,:;/+-_"
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_A_NUMBER = re.compile(rf"[+-]?{_NUMBER}(?:[-/]{_NUMBER})*%?")
_A_RECORD_LINK = re.compile(r"\[(?P<record_id>[^\[\]\s]+)\]\([^()\s]+\)")


def render_note(note: str, facts: TurnFacts) -> str:
    links = {s.record_id: s.url for s in reversed(facts.citable_records())}

    def linked(match: re.Match[str]) -> str:
        record_id = match.group("record_id")
        url = links.get(record_id)
        gap = match.group("gap")
        return "" if url is None else f"{gap}[{record_id}]({url})"

    return A_RECORD.sub(linked, without_links(note))


def linked_records(rendered: str) -> list[str]:
    found = (m.group("record_id") for m in _A_RECORD_LINK.finditer(rendered))
    return list(dict.fromkeys(found))


def _tokens(text: str) -> list[str]:
    return [found.strip(_EDGE_MARKS) for found in _A_TOKEN.findall(text)]


def written_numbers(text: str, said: frozenset[str] = frozenset()) -> list[str]:
    plain = without_item_numbers(A_RECORD.sub(" ", text))
    written = (
        token
        for token in _tokens(plain)
        if _A_NUMBER.fullmatch(token) and token.casefold() not in said
    )
    return list(dict.fromkeys(written))


def note_facts(note: str, facts: TurnFacts) -> list[str]:
    plain = A_RECORD.sub(" ", note)
    links = list(dict.fromkeys(written_links(plain)))
    if not facts.holds_site_data():
        return links
    said = frozenset(
        token.casefold()
        for message in facts.request_messages
        for token in _tokens(message)
    )
    return [*links, *written_numbers(without_links(plain), said)]


__all__ = [
    "A_RECORD",
    "linked_records",
    "note_facts",
    "render_note",
    "written_numbers",
]
