"""What FRAME's instructions pin, read back: the parameter sheets it copies a
value from, and the criteria its workspace holds bound."""

from __future__ import annotations

import re

from pydantic import TypeAdapter
from veupathdb_mcp.catalog import SheetEntry

_ENTRIES = TypeAdapter(list[SheetEntry])
_WORKSPACE_HEAD = "# FRAME workspace (in-progress spec)"
_WORKSPACE_END = "structure_set="
_HELD = re.compile(r"^- \[(?P<cid>[^\]]+)\]")
_STRAIN_WORDS = 3
# The name parts that pair a reference parameter with its comparison.
_REFERENCE = "_ref_"
_COMPARISON = "_comp_"


def _workspace_lines(instructions: str) -> list[str]:
    """The lines of the pinned FRAME workspace, or none when none is pinned."""
    lines = instructions.splitlines()
    if _WORKSPACE_HEAD not in lines:
        return []
    held: list[str] = []
    for line in lines[lines.index(_WORKSPACE_HEAD) + 1 :]:
        if line.startswith(_WORKSPACE_END):
            break
        held.append(line)
    return held


def workspace_criteria(instructions: str) -> frozenset[str]:
    """The criteria the pinned FRAME workspace holds bound, by id."""
    found = (_HELD.match(line) for line in _workspace_lines(instructions))
    return frozenset(m.group("cid") for m in found if m is not None)


def workspace_search(instructions: str, criterion_id: str) -> str | None:
    """The search the pinned FRAME workspace holds ``criterion_id`` bound to."""
    runs = re.compile(rf"^- \[{re.escape(criterion_id)}\] .* -> (?P<search>\S+)")
    found = (runs.match(line) for line in _workspace_lines(instructions))
    return next((m.group("search") for m in found if m is not None), None)


def sheet_entries(instructions: str, criterion_id: str) -> list[SheetEntry]:
    """The entries of the sheet pinned for one criterion, or none."""
    lines = instructions.splitlines()
    head = f"### sheet for {criterion_id} -> "
    start = next((i for i, line in enumerate(lines) if line.startswith(head)), None)
    if start is None:
        return []
    for line in lines[start + 1 :]:
        if line.startswith("###"):
            return []
        if line.startswith("["):
            return _ENTRIES.validate_json(line)
    return []


def _names_a_strain(value: str) -> bool:
    """A tree entry below the species level: genus, species and strain words."""
    return len(value.split()) >= _STRAIN_WORDS


def alt_organism(
    instructions: str, criterion_id: str, organism: str, *, same_genus: bool
) -> str:
    """The first strain of the criterion's sheet in the genus of ``organism``,
    or outside it when not ``same_genus``, else its first other strain, else
    its first other entry."""
    entry = next(
        (e for e in sheet_entries(instructions, criterion_id) if e.name == "organism"),
        None,
    )
    if entry is None:
        msg = f"No organism sheet is pinned for {criterion_id}"
        raise LookupError(msg)
    others = [option.value for option in entry.vocabulary if option.value != organism]
    strains = [value for value in others if _names_a_strain(value)]
    genus = f"{organism.split(' ', maxsplit=1)[0]} "
    matching = [value for value in strains if value.startswith(genus) == same_genus]
    chosen = (matching or strains or others)[:1]
    if not chosen:
        msg = f"The sheet of {criterion_id} lists no organism besides {organism}"
        raise LookupError(msg)
    return chosen[0]


def _count_in(label: str) -> int:
    """The count a label ends with, as ``<term> : <name> : <count>``, else 0."""
    tail = label.rsplit(":", maxsplit=1)[-1].strip()
    return int(tail) if tail.isdigit() else 0


def richest_value(instructions: str, criterion_id: str, name: str) -> str:
    """The entry of one parameter of the criterion's sheet whose label counts
    the most records, else its first entry."""
    entry = next(
        (e for e in sheet_entries(instructions, criterion_id) if e.name == name), None
    )
    if entry is None or not entry.vocabulary:
        msg = f"The sheet of {criterion_id} lists no value for {name}"
        raise LookupError(msg)
    richest = max(entry.vocabulary, key=lambda option: _count_in(option.display))
    return richest.value


def outside_value(
    instructions: str, criterion_id: str, name: str, choices: tuple[str, ...]
) -> str:
    """The first of ``choices`` the criterion's sheet does not list for ``name``."""
    entry = next(
        (e for e in sheet_entries(instructions, criterion_id) if e.name == name), None
    )
    listed = set() if entry is None else {option.value for option in entry.vocabulary}
    outside = [choice for choice in choices if choice not in listed]
    if not outside:
        msg = f"The sheet of {criterion_id} lists every choice for {name}"
        raise LookupError(msg)
    return outside[0]


def contrast_values(instructions: str, criterion_id: str) -> dict[str, list[str]]:
    """One group per side of each reference and comparison pair the pinned
    sheet lists: the reference takes the first group of its vocabulary, and
    the comparison the first group of its own that differs from it."""
    entries = {e.name: e for e in sheet_entries(instructions, criterion_id)}
    values: dict[str, list[str]] = {}
    for name, entry in entries.items():
        partner = entries.get(name.replace(_REFERENCE, _COMPARISON))
        if _REFERENCE not in name or partner is None or not entry.vocabulary:
            continue
        reference = entry.vocabulary[0].value
        other = [o.value for o in partner.vocabulary if o.value != reference]
        if other:
            values[name] = [reference]
            values[partner.name] = [other[0]]
    return values
