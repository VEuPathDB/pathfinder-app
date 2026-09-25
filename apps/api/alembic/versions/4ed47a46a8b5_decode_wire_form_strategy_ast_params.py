"""decode_wire_form_strategy_ast_params

Revision ID: 4ed47a46a8b5
Revises: 2026_04_22_0001
Create Date: 2026-04-23 02:51:36.953271

Recursively walk every persisted ``conversations.strategy_ast`` and decode
WDK-wire-format string values back into native Python types. Pre-fix WDK
sync wrote JSON-encoded strings (e.g. ``"[\\"Plasmodium\\"]"``) into
``parameters``; the canonicalizer now expects native shapes (lists, dicts,
scalars). Idempotent — already-decoded values pass through unchanged.
"""

from __future__ import annotations

import json

import sqlalchemy
from alembic import op

import pathfinder.persistence.models  # noqa: F401 — registers GUID type

revision: str = "4ed47a46a8b5"
down_revision: str | None = "2026_04_22_0001"
branch_labels: str | None = None
depends_on: str | None = None

_MIN_JSON_WRAPPER_LEN = 2


def _decode_wire_value(value: object) -> object:
    """Decode one wire-form value to its native Python type."""
    if not isinstance(value, str):
        return value
    if len(value) < _MIN_JSON_WRAPPER_LEN:
        return value
    if value[0] not in "[{" or value[-1] not in "]}":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError, ValueError:
        return value


def _decode_node(node: object) -> tuple[object, bool]:
    """Recursively decode a strategy AST node. Returns (new_node, changed)."""
    if not isinstance(node, dict):
        return node, False
    changed = False
    new_node: dict[str, object] = {}
    for key, value in node.items():
        if key == "parameters" and isinstance(value, dict):
            new_params: dict[str, object] = {}
            param_changed = False
            for pname, pval in value.items():
                decoded = _decode_wire_value(pval)
                new_params[pname] = decoded
                if decoded is not pval:
                    param_changed = True
            new_node[key] = new_params
            if param_changed:
                changed = True
        elif (
            key
            in ("primaryInput", "secondaryInput", "primary_input", "secondary_input")
            and value is not None
        ):
            new_child, child_changed = _decode_node(value)
            new_node[key] = new_child
            if child_changed:
                changed = True
        else:
            new_node[key] = value
    return new_node, changed


def upgrade() -> None:
    """Backfill decoded form into every conversations.strategy_ast row."""
    bind = op.get_bind()
    rows = bind.execute(
        sqlalchemy.text(
            "SELECT id, strategy_ast FROM conversations "
            "WHERE strategy_ast IS NOT NULL AND strategy_ast != '{}'::jsonb"
        ),
    ).fetchall()

    update_stmt = sqlalchemy.text(
        "UPDATE conversations SET strategy_ast = :ast WHERE id = :id",
    )
    for row in rows:
        ast = dict(row.strategy_ast)
        root = ast.get("root")
        if root is None:
            continue
        new_root, changed = _decode_node(root)
        if not changed:
            continue
        ast["root"] = new_root
        bind.execute(
            update_stmt,
            {"id": row.id, "ast": json.dumps(ast)},
        )


def downgrade() -> None:
    """No-op — re-encoding to wire form would silently corrupt single-pick
    strings that happen to look like JSON. The forward direction is safe
    (idempotent); reverse is not."""
