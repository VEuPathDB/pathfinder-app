from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_GENERIC = "An internal error occurred"
_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/2026_11_03_0002_old_audit_rows_hold_no_raw_error.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("old_audit_rows_text", _MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _migration()


@pytest.mark.parametrize(
    ("note", "cleaned"),
    [
        (
            "NF54: failed (VEuPathDB service error: GET /x?k=S -> HTTP 422 (ERROR): bad)",
            f"NF54: failed ({_GENERIC})",
        ),
        ("(x https://a?k=S (see docs))", _GENERIC),
        ("NF54: failed (https://a)", f"NF54: failed ({_GENERIC})"),
        ("NF54: failed (Data parsing failed: x)", f"NF54: failed ({_GENERIC})"),
        ("2 candidates in 1 genome, 1 sampled", "2 candidates in 1 genome, 1 sampled"),
        (
            "NF54: failed (the site answered 503)",
            "NF54: failed (the site answered 503)",
        ),
    ],
)
def test_a_stage_note_keeps_only_its_written_head(note: str, cleaned: str) -> None:
    assert MIGRATION.clean_stage_note(note) == cleaned
    assert MIGRATION.clean_stage_note(cleaned) == cleaned


@pytest.mark.parametrize(
    ("message", "cleaned"),
    [
        ("boom; api_key=S; https://a", f"boom; {_GENERIC}"),
        ("read failed with api_key=S", _GENERIC),
        ("read /answer?token=S failed", _GENERIC),
        ("read /answer?a=1&k=S failed", _GENERIC),
        ("a bare body with no marker", "a bare body with no marker"),
        ("the rate a=b is written", "the rate a=b is written"),
    ],
)
def test_a_segment_holding_a_key_or_a_query_is_cleaned(
    message: str, cleaned: str
) -> None:
    assert MIGRATION.clean_text(message) == cleaned
    assert MIGRATION.clean_text(cleaned) == cleaned
