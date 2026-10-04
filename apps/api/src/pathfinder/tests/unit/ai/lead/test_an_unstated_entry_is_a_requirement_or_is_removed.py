"""FRAME's unstated list holds only requirements the researcher wrote: the field
says a note is no requirement, and a refusal of an unwritten entry offers both
ways out, the researcher's words or removing the entry."""

from __future__ import annotations

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import unwritten_requirements_refusal

_NOTE = (
    "The edited strategy's new result count cannot be reported until the strategy "
    "is rebuilt and executed."
)


def test_a_refused_entry_is_restated_or_removed() -> None:
    assert unwritten_requirements_refusal([_NOTE]) == (
        f"unstated names {[_NOTE]}, which no message of the researcher states. "
        "Each entry is a requirement of the request that no search on the site "
        "states, in the words the researcher wrote it in. Restate a requirement "
        "in those words, and remove an entry that names no requirement of the "
        "request, such as a note about a count, the build or a later step."
    )


def test_the_field_says_a_note_is_no_requirement() -> None:
    described = FrameResult.model_fields["unstated"].description or ""

    assert described.endswith(
        "A note about a count, the build or a later step is no requirement and "
        "is never listed."
    )
