"""A stored synthesis summary holds its values in place and no facts.

Revision ID: 2026_10_30_0001
Revises: 2026_10_24_0003
"""

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy
from alembic import op
from pydantic import BaseModel, ConfigDict, Field

revision: str = "2026_10_30_0001"
down_revision: str | Sequence[str] | None = "2026_10_24_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_A_CITE = re.compile(r"[ \t]*\[cite:(?P<body>[^\[\]\n]+)\]")
_A_STAT = re.compile(r"\[stat:(?P<body>[^\[\]\n]+)\]")
_UNHELD = "a value not shown"


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: str


class _Fact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    rows: list[_Row] = Field(default_factory=list)


class _Stored(BaseModel):
    model_config = ConfigDict(extra="allow")

    summary: str
    facts: list[_Fact] = Field(default_factory=list)


def _value(facts: Sequence[_Fact], body: str) -> str | None:
    held_id, _, name = body.partition(".")
    held = next((f for f in reversed(facts) if f.id == held_id), None)
    rows = [] if held is None else held.rows
    return next((row.value for row in rows if row.name == name), None)


def rendered(stored: dict[str, Any]) -> dict[str, Any]:
    synthesis = _Stored.model_validate(stored)

    def cited(match: re.Match[str]) -> str:
        value = _value(synthesis.facts, match.group("body"))
        return "" if value is None else f" ({value})"

    def stated(match: re.Match[str]) -> str:
        value = _value(synthesis.facts, match.group("body"))
        return _UNHELD if value is None else value

    summary = _A_STAT.sub(stated, _A_CITE.sub(cited, synthesis.summary))
    kept = synthesis.model_dump(exclude={"facts"})
    return {**kept, "summary": summary}


def upgrade() -> None:
    connection = op.get_bind()
    stored = connection.execute(
        sqlalchemy.text(
            "SELECT id, synthesis FROM audit_runs WHERE synthesis IS NOT NULL"
        )
    ).all()
    for run_id, synthesis in stored:
        connection.execute(
            sqlalchemy.text(
                "UPDATE audit_runs SET synthesis = CAST(:synthesis AS jsonb) "
                "WHERE id = :id"
            ),
            {"id": run_id, "synthesis": json.dumps(rendered(synthesis))},
        )


def downgrade() -> None:
    pass
