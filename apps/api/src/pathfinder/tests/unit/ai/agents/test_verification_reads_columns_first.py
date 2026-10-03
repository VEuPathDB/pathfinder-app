"""VERIFY reads each search step's columns first and samples the root only for a
criterion no column shows."""

from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS

_TEXT = " ".join(_VERIFICATION_INSTRUCTIONS.split())


def test_the_columns_are_read_before_any_sample() -> None:
    columns = _TEXT.index("Read the columns first: call ``read_step_columns``")
    sample = _TEXT.index("Sample only where no column shows")

    assert columns < sample


def test_the_runtime_states_a_column_short_of_every_gene() -> None:
    assert (
        "states every column that falls short of all genes, or that the site "
        "does not show, as a caveat"
    ) in _TEXT


def test_a_note_that_names_a_step_samples_that_step() -> None:
    assert (
        "call ``get_sample_records`` with the ``wdk_step_id`` the note names, "
        "else the root's, and ``limit`` 8"
    ) in _TEXT
