"""The usage report prints each grouping and the averages."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pathfinder.devtools.usage import build_report, render
from pathfinder.persistence.repositories.usage_report import TurnUsageRow

_THREAD = UUID("12121212-1212-1212-1212-121212121212")
_USER = UUID("34343434-3434-3434-3434-343434343434")


def _row(cost: str) -> TurnUsageRow:
    return TurnUsageRow(
        conversation_id=_THREAD,
        conversation_name="kinases",
        site_id="plasmodb",
        assistant_id="pathfinder",
        user_id=_USER,
        user_external_id=None,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        total_tokens=100,
        cost_usd=Decimal(cost),
    )


def test_the_text_names_the_thread_its_site_and_its_researcher() -> None:
    text = render(build_report([_row("0.0100"), _row("0.0300")]))

    assert (
        f"     2          200     0.0400  kinases  [plasmodb pathfinder {_USER}]"
        in text
    )
    assert "cost per turn          0.0200 USD" in text
    assert "turns per conversation 2.00" in text


def test_an_empty_database_averages_to_zero() -> None:
    report = build_report([])

    assert (report.cost_per_turn, report.turns_per_conversation) == (
        Decimal(0),
        Decimal(0),
    )
