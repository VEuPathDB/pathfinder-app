"""A frame pass that leaves one value open and asks it, as the frame tool
answers it."""

from __future__ import annotations

from pathfinder.tests.unit.ai.models._mock_turns import SHEET_ORGANISMS

ASKED_ORGANISM = "Which organism should the signal peptide search read?"


def asking_frame(site_id: str) -> dict[str, object]:
    """A frame pass that leaves the organism open and asks it with the options
    its sheet offers, the site organism recommended."""
    options = SHEET_ORGANISMS[site_id]
    return {
        "summary": "The signal peptide search needs its organism.",
        "disposition": "needs_user",
        "openQuestions": [
            {
                "question": ASKED_ORGANISM,
                "dimension": "organism",
                "recommendedValue": options[0],
                "options": options,
            }
        ],
    }
