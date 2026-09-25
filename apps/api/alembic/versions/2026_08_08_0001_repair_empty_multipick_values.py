"""Repair multi-pick values stored as the literal string "[]".

``MultiPickValue.values`` used to require at least one entry, so callers with
nothing selected degraded the empty list to the string ``"[]"``. That reached
vocabulary matching and WDK rejected it with
``Parameter '<name>' does not accept '[]'`` - on parameters whose own spec
sets ``allowEmptyValue=true``. The type now allows an empty list; rows written
before that still carry the bad value, which makes their step editor
unopenable without the read-path leniency that exists to tolerate it.

Revision ID: 2026_08_08_0001
Revises: 2026_08_07_0001
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy
from alembic import op

revision: str = "2026_08_08_0001"
down_revision: str | None = "2026_08_07_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _repair(node: Any) -> tuple[Any, int]:
    """Walk the AST, replacing ``values: ["[]"]`` with ``values: []``.

    Structural rather than a regex over the serialized text: jsonb normalizes
    key order and spacing, so the textual shape is not something to match on.
    A multi-pick holding real terms alongside ``"[]"`` is not something the
    old degradation could produce, so only the sole-element case is touched.
    """
    fixed = 0
    if isinstance(node, list):
        out_list = []
        for item in node:
            repaired, count = _repair(item)
            out_list.append(repaired)
            fixed += count
        return out_list, fixed
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if (
                key == "values"
                and node.get("type") == "multi-pick-vocabulary"
                and value == ["[]"]
            ):
                out[key] = []
                fixed += 1
                continue
            repaired, count = _repair(value)
            out[key] = repaired
            fixed += count
        return out, fixed
    return node, fixed


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sqlalchemy.text(
            "SELECT id, strategy_ast FROM conversations "
            "WHERE strategy_ast::text LIKE '%\"[]\"%'"
        )
    ).fetchall()

    for row in rows:
        repaired, fixed = _repair(row.strategy_ast)
        if fixed == 0:
            continue
        connection.execute(
            sqlalchemy.text(
                "UPDATE conversations SET strategy_ast = CAST(:ast AS jsonb) "
                "WHERE id = :id"
            ),
            {"ast": json.dumps(repaired), "id": row.id},
        )


def downgrade() -> None:
    """No downgrade: the empty list is the correct value, and restoring the
    corrupt one would only re-break the affected steps."""
