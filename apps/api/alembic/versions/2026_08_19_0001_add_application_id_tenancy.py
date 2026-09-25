"""add_application_id_tenancy

Revision ID: 2026_08_19_0001
Revises: 2026_08_09_0001
Create Date: 2026-08-19 00:00:00.000000

The downgrade moves back only the memories of the default application; another
application's memories keep their namespace and are unreachable by the old
code, which is the honest outcome of removing the column that named them.
"""

from collections.abc import Sequence

import sqlalchemy
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "2026_08_19_0001"
down_revision: str | Sequence[str] | None = "2026_08_09_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_APPLICATION_ID = "pathfinder"
USER_SEGMENT = "user."
APPLICATION_SEGMENT = f"app.{DEFAULT_APPLICATION_ID}."

_OWNED_TABLES: tuple[str, ...] = (
    "conversations",
    "gene_sets",
    "control_sets",
    "experiments",
    "memory_tombstones",
    "monthly_usage",
)

# A memory is keyed by its dot-joined namespace, so moving it under the
# application rewrites that prefix. store_vectors references store(prefix, key)
# with no ON UPDATE action, so the new rows land before the old ones go.
_STORE_TABLES: tuple[str, ...] = ("store", "store_vectors")

_DELETE_OLD_STORE_ROWS = "DELETE FROM store WHERE prefix LIKE :old_like"


def _table_exists(connection: Connection, name: str) -> bool:
    found = connection.scalar(
        sqlalchemy.text("SELECT to_regclass(:qualified)"),
        {"qualified": f"public.{name}"},
    )
    return found is not None


def _column_names(connection: Connection, table: str) -> list[str]:
    rows = connection.execute(
        sqlalchemy.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table "
            "ORDER BY ordinal_position",
        ),
        {"table": table},
    )
    return [str(row[0]) for row in rows]


def _copy_statement(table: str, columns: list[str]) -> sqlalchemy.Insert:
    """Copy every column the table has, so no value can be left behind.

    The column list comes from the catalog because the store DDL grows over
    releases (expiry and TTL arrived after the first one). A conflicting row
    raises instead of being skipped, so the delete that follows can never
    remove a memory that was not copied.
    """
    store = sqlalchemy.table(table, *(sqlalchemy.column(name) for name in columns))
    moved_prefix = sqlalchemy.bindparam(
        "add", type_=sqlalchemy.String
    ) + sqlalchemy.func.substr(
        store.c.prefix,
        sqlalchemy.bindparam("cut", type_=sqlalchemy.Integer),
    )
    selected = [
        moved_prefix if column == "prefix" else store.c[column] for column in columns
    ]
    return sqlalchemy.insert(store).from_select(
        columns,
        sqlalchemy.select(*selected).where(
            store.c.prefix.like(
                sqlalchemy.bindparam("old_like", type_=sqlalchemy.String)
            ),
        ),
    )


def move_store_namespaces(
    connection: Connection,
    *,
    matching: str,
    prepend: str = "",
    drop: str = "",
) -> None:
    """Move every memory whose prefix starts with ``matching``.

    The new prefix is ``prepend`` followed by the old one without its leading
    ``drop``. The store tables are created by the memory lifespan, not by
    alembic, so a database that has never opened the store has nothing to move.
    """
    if not _table_exists(connection, "store"):
        return
    params = {"add": prepend, "cut": len(drop) + 1, "old_like": f"{matching}%"}
    for table in _STORE_TABLES:
        if not _table_exists(connection, table):
            continue
        columns = _column_names(connection, table)
        connection.execute(_copy_statement(table, columns), params)
    connection.execute(
        sqlalchemy.text(_DELETE_OLD_STORE_ROWS),
        {"old_like": params["old_like"]},
    )


def upgrade() -> None:
    for table in _OWNED_TABLES:
        op.add_column(
            table,
            sqlalchemy.Column(
                "application_id",
                sqlalchemy.String(length=64),
                nullable=False,
                server_default=DEFAULT_APPLICATION_ID,
            ),
        )

    op.drop_index("ix_conversations_user_site", table_name="conversations")
    op.create_index(
        "ix_conversations_user_app_site",
        "conversations",
        ["user_id", "application_id", "site_id"],
    )
    op.drop_index("ix_gene_sets_user_site", table_name="gene_sets")
    op.create_index(
        "ix_gene_sets_user_app_site",
        "gene_sets",
        ["user_id", "application_id", "site_id"],
    )
    op.drop_index("ix_experiments_user_id", table_name="experiments")
    op.create_index(
        "ix_experiments_user_app",
        "experiments",
        ["user_id", "application_id"],
    )
    op.drop_index("ix_control_sets_site_id", table_name="control_sets")
    op.create_index(
        "ix_control_sets_site_app",
        "control_sets",
        ["site_id", "application_id"],
    )

    op.drop_constraint(
        "uq_tombstones_user_kind_hash",
        "memory_tombstones",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_tombstones_user_app_kind_hash",
        "memory_tombstones",
        ["user_id", "application_id", "kind", "content_hash"],
    )
    op.drop_constraint(
        "monthly_usage_user_period_key",
        "monthly_usage",
        type_="unique",
    )
    op.create_unique_constraint(
        "monthly_usage_user_app_period_key",
        "monthly_usage",
        ["user_id", "application_id", "period_start"],
    )

    move_store_namespaces(
        op.get_bind(),
        matching=USER_SEGMENT,
        prepend=APPLICATION_SEGMENT,
    )


def downgrade() -> None:
    move_store_namespaces(
        op.get_bind(),
        matching=f"{APPLICATION_SEGMENT}{USER_SEGMENT}",
        drop=APPLICATION_SEGMENT,
    )

    op.drop_constraint(
        "monthly_usage_user_app_period_key",
        "monthly_usage",
        type_="unique",
    )
    op.create_unique_constraint(
        "monthly_usage_user_period_key",
        "monthly_usage",
        ["user_id", "period_start"],
    )
    op.drop_constraint(
        "uq_tombstones_user_app_kind_hash",
        "memory_tombstones",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_tombstones_user_kind_hash",
        "memory_tombstones",
        ["user_id", "kind", "content_hash"],
    )

    op.drop_index("ix_control_sets_site_app", table_name="control_sets")
    op.create_index("ix_control_sets_site_id", "control_sets", ["site_id"])
    op.drop_index("ix_experiments_user_app", table_name="experiments")
    op.create_index("ix_experiments_user_id", "experiments", ["user_id"])
    op.drop_index("ix_gene_sets_user_app_site", table_name="gene_sets")
    op.create_index("ix_gene_sets_user_site", "gene_sets", ["user_id", "site_id"])
    op.drop_index("ix_conversations_user_app_site", table_name="conversations")
    op.create_index(
        "ix_conversations_user_site",
        "conversations",
        ["user_id", "site_id"],
    )

    for table in reversed(_OWNED_TABLES):
        op.drop_column(table, "application_id")
