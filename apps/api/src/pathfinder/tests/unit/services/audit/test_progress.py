"""The words a stage lane says while it waits for a site."""

from __future__ import annotations

from pathfinder.services.audit.progress import waiting


def test_a_pause_names_the_site_and_what_it_waits_for() -> None:
    assert waiting("plasmodb", 30.0, 1, "finding") == (
        "waiting 30 s for plasmodb, 1 finding unanswered"
    )
    assert waiting("toxodb", 900.0, 2, "genome") == (
        "waiting 900 s for toxodb, 2 genomes unanswered"
    )
