"""The count of rows a write statement changed."""

from __future__ import annotations

from types import SimpleNamespace

from pathfinder.persistence.rows import rows_changed


def test_rows_changed_reads_the_row_count_and_counts_none_as_zero() -> None:
    assert rows_changed(SimpleNamespace(rowcount=3)) == 3
    assert rows_changed(SimpleNamespace(rowcount=None)) == 0
