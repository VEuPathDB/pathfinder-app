from __future__ import annotations

from pathfinder.domain.scratchpad.models import Note

_EMPTY_PHASE_BLOCK = (
    "## Scratchpad (empty)\n\n"
    "No notes yet. As you work, call note(...) to save:\n"
    "  - interesting searches and their params\n"
    "  - dead ends (so you don't retry them)\n"
    "  - assumptions about the user's intent\n"
    "  - decisions and why you made them\n\n"
    "Rule: Before moving on from any promising search or parameter trial, "
    "call note(...)."
)

_EMPTY_SUPERVISOR_BLOCK = "## Scratchpad\n\n(empty)"

_RULE_TAIL = (
    "\n\n"
    "Rule: Before moving on from any promising search or parameter trial, "
    "call note(...).\n"
    "      Before ending your turn, review notes (list_notes/search_notes) "
    "and pin_note(...) load-bearing findings.\n"
    "      In your typed delta, reference supporting notes via note_refs "
    "when possible."
)


def _format_entry(note: Note) -> str:
    return f"  [{note.id}] {note.title}\n             {note.summary}"


def _split_pinned(notes: list[Note]) -> tuple[list[Note], list[Note]]:
    pinned = [n for n in notes if n.pinned]
    recent = [n for n in notes if not n.pinned]
    return pinned, recent


def _render_core(
    notes: list[Note],
    *,
    total_count: int,
    budget_chars: int,
    include_rule: bool,
) -> str:
    pinned, recent = _split_pinned(notes)
    header = f"## Scratchpad ({total_count} notes, {len(pinned)} pinned)"

    def _assemble(recent_subset: list[Note]) -> str:
        sections: list[str] = [header]
        if pinned:
            sections.append("### Pinned")
            sections.extend(_format_entry(n) for n in pinned)
        if recent_subset:
            sections.append("### Recent")
            sections.extend(_format_entry(n) for n in recent_subset)
        body = "\n".join(sections)
        if include_rule:
            body = body + _RULE_TAIL
        return body

    # Drop oldest non-pinned until within budget (pinned always kept).
    trimmed = list(recent)
    while trimmed and len(_assemble(trimmed)) > budget_chars:
        trimmed.pop()  # list is newest→oldest; pop() removes oldest
    return _assemble(trimmed)


def render_scratchpad_for_phase(
    notes: list[Note],
    *,
    total_count: int,
    budget_chars: int = 10000,
) -> str:
    if total_count == 0:
        return _EMPTY_PHASE_BLOCK
    return _render_core(
        notes,
        total_count=total_count,
        budget_chars=budget_chars,
        include_rule=True,
    )
