"""What PathFinder tells a sub-agent about keeping notes.

The runtime renders the index and defines the tools; the coaching is this
product's, because it names the work a pathogen researcher's agent does.
"""

from __future__ import annotations

from assistant_core.scratchpad.rendering import ScratchpadGuidance

from pathfinder.domain.memory import MemoryKind

# The memory kind a promoted note is written under.
PROMOTED_NOTE_KIND: MemoryKind = "knowledge"

PATHFINDER_SCRATCHPAD_GUIDANCE = ScratchpadGuidance(
    empty=(
        "As you work, call note(...) to save:\n"
        "  - interesting searches and their params\n"
        "  - dead ends (so you don't retry them)\n"
        "  - assumptions about the user's intent\n"
        "  - decisions and why you made them\n\n"
        "Rule: Before moving on from any promising search or parameter trial, "
        "call note(...)."
    ),
    populated=(
        "Rule: Before moving on from any promising search or parameter trial, "
        "call note(...).\n"
        "      Before ending your turn, review notes (list_notes/search_notes) "
        "and pin_note(...) load-bearing findings.\n"
        "      In your typed delta, reference supporting notes via note_refs "
        "when possible."
    ),
    promote=(
        "Use when a note captures reusable biological knowledge that is worth "
        "remembering beyond this conversation: a mechanism, a named marker "
        "set, a fact about an organism."
    ),
)
