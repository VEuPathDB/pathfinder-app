"""Cost and tokens per conversation, per researcher and per day, from the database.

Usage::

    python -m pathfinder.devtools.usage report [--since 2026-10-01] [--site plasmodb]
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from pydantic import BaseModel, ConfigDict

from pathfinder.persistence.repositories.usage_report import (
    TurnUsageRow,
    UsageReportRepository,
)


class UsageLine(BaseModel):
    """One group's turns, tokens and cost."""

    model_config = ConfigDict(frozen=True)

    label: str
    turns: int
    total_tokens: int
    cost_usd: Decimal


class ConversationLine(UsageLine):
    """One conversation's totals, with where and by whom it ran."""

    site_id: str
    assistant_id: str
    user: str


class UsageReport(BaseModel):
    """Every grouping the report prints, and the averages over conversations."""

    model_config = ConfigDict(frozen=True)

    conversations: list[ConversationLine]
    users: list[UsageLine]
    days: list[UsageLine]
    turns_per_conversation: Decimal
    cost_per_conversation: Decimal
    cost_per_turn: Decimal


def _user(row: TurnUsageRow) -> str:
    return row.user_external_id or str(row.user_id)


def _grouped[KeyT](
    rows: Iterable[TurnUsageRow], key: Callable[[TurnUsageRow], KeyT]
) -> dict[KeyT, list[TurnUsageRow]]:
    groups: dict[KeyT, list[TurnUsageRow]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return dict(groups)


def _line(label: str, rows: Sequence[TurnUsageRow]) -> UsageLine:
    return UsageLine(
        label=label,
        turns=len(rows),
        total_tokens=sum(row.total_tokens for row in rows),
        cost_usd=sum((row.cost_usd for row in rows), Decimal(0)),
    )


def _ratio(numerator: Decimal, denominator: int) -> Decimal:
    return numerator / denominator if denominator else Decimal(0)


def build_report(rows: Sequence[TurnUsageRow]) -> UsageReport:
    """Group the turns by conversation, by researcher and by UTC day."""
    by_conversation: dict[UUID, list[TurnUsageRow]] = _grouped(
        rows, lambda row: row.conversation_id
    )
    conversations = [
        ConversationLine(
            **_line(turns[0].conversation_name or str(cid), turns).model_dump(),
            site_id=turns[0].site_id,
            assistant_id=turns[0].assistant_id,
            user=_user(turns[0]),
        )
        for cid, turns in by_conversation.items()
    ]
    total_cost = sum((row.cost_usd for row in rows), Decimal(0))
    return UsageReport(
        conversations=sorted(conversations, key=lambda line: -line.cost_usd),
        users=[_line(user, turns) for user, turns in _grouped(rows, _user).items()],
        days=[
            _line(day.isoformat(), turns)
            for day, turns in sorted(
                _grouped(rows, lambda row: row.created_at.date()).items()
            )
        ],
        turns_per_conversation=_ratio(Decimal(len(rows)), len(conversations)),
        cost_per_conversation=_ratio(total_cost, len(conversations)),
        cost_per_turn=_ratio(total_cost, len(rows)),
    )


def _conversation_name(line: ConversationLine) -> str:
    return f"{line.label}  [{line.site_id} {line.assistant_id} {line.user}]"


def _table[LineT: UsageLine](
    title: str,
    lines: Sequence[LineT],
    name: Callable[[LineT], str] = lambda line: line.label,
) -> list[str]:
    out = [f"\n{title}", f"{'turns':>6} {'tokens':>12} {'cost_usd':>10}  name"]
    out.extend(
        f"{line.turns:>6} {line.total_tokens:>12} {line.cost_usd:>10.4f}  {name(line)}"
        for line in lines
    )
    return out


def render(report: UsageReport) -> str:
    """The report as plain text tables."""
    lines = [
        *_table("Per conversation", report.conversations, _conversation_name),
        *_table("Per researcher", report.users),
        *_table("Per day (UTC)", report.days),
        "\nAverages",
        f"  turns per conversation {report.turns_per_conversation:.2f}",
        f"  cost per conversation  {report.cost_per_conversation:.4f} USD",
        f"  cost per turn          {report.cost_per_turn:.4f} USD",
    ]
    return "\n".join(lines)


async def _report(since: date | None, site_id: str | None) -> str:
    async with async_session_factory() as session:
        rows = await UsageReportRepository(session).turns(since=since, site_id=site_id)
    return render(build_report(rows))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pathfinder.devtools.usage")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="Print cost and tokens by group.")
    report.add_argument("--since", type=date.fromisoformat, default=None)
    report.add_argument("--site", default=None)
    args = parser.parse_args(argv)
    print(asyncio.run(_report(args.since, args.site)))


if __name__ == "__main__":
    main()
