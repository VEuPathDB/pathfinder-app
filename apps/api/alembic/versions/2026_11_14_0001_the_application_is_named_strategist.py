from collections.abc import Sequence

import sqlalchemy
from alembic import op
from cryptography.exceptions import InvalidTag

from strategist.platform.config import get_settings
from strategist.platform.provider_key_cipher import key_aad

revision: str = "2026_11_14_0001"
down_revision: str | Sequence[str] | None = "2026_11_13_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = sqlalchemy.text(
    "SELECT table_name FROM information_schema.columns "
    "WHERE column_name = 'application_id' AND table_schema = current_schema() "
    "ORDER BY table_name"
)
_SEALED_KEYS = sqlalchemy.text(
    "SELECT id, user_id, provider, ciphertext FROM user_provider_keys "
    "WHERE application_id = :old AND ciphertext IS NOT NULL"
)
_RESEAL = sqlalchemy.text(
    "UPDATE user_provider_keys SET ciphertext = :ciphertext WHERE id = :id"
)
_DEFAULTS = sqlalchemy.text(
    "SELECT table_name, column_name FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND column_default LIKE :pattern"
)
_STORE_COLUMNS = sqlalchemy.text(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = :table "
    "ORDER BY ordinal_position"
)
_STORE_TABLES = ("store", "store_vectors")


def _reseal_provider_keys(old: str, new: str) -> None:
    connection = op.get_bind()
    sealed = connection.execute(_SEALED_KEYS.bindparams(old=old)).all()
    if not sealed:
        return
    cipher = get_settings().provider_key_cipher
    if cipher is None:
        msg = "PROVIDER_KEY_ENCRYPTION_KEY is needed to reseal the stored provider keys"
        raise RuntimeError(msg)
    for key_id, user_id, provider, ciphertext in sealed:
        try:
            resealed = cipher.reseal(
                ciphertext,
                old_aad=key_aad(user_id, old, provider),
                new_aad=key_aad(user_id, new, provider),
            )
        except InvalidTag:
            continue
        connection.execute(_RESEAL.bindparams(ciphertext=resealed, id=key_id))


def _move_memories(old: str, new: str) -> None:
    connection = op.get_bind()
    old_prefix = f"app.{old}."
    for name in _STORE_TABLES:
        names = connection.execute(_STORE_COLUMNS.bindparams(table=name)).scalars()
        columns = list(names)
        if not columns:
            return
        table = sqlalchemy.table(name, *(sqlalchemy.column(c) for c in columns))
        moved = sqlalchemy.literal(f"app.{new}.") + sqlalchemy.func.substr(
            table.c.prefix, len(old_prefix) + 1
        )
        connection.execute(
            sqlalchemy.insert(table).from_select(
                columns,
                sqlalchemy.select(
                    *(moved if c == "prefix" else table.c[c] for c in columns)
                ).where(table.c.prefix.startswith(old_prefix, autoescape=True)),
            )
        )
    for name in reversed(_STORE_TABLES):
        table = sqlalchemy.table(name, sqlalchemy.column("prefix"))
        connection.execute(
            sqlalchemy.delete(table).where(
                table.c.prefix.startswith(old_prefix, autoescape=True)
            )
        )


def _move_defaults(old: str, new: str) -> None:
    connection = op.get_bind()
    found = connection.execute(_DEFAULTS.bindparams(pattern=f"'{old}'::%")).all()
    for table, column in found:
        op.alter_column(table, column, server_default=new)


def _rename(old: str, new: str) -> None:
    _reseal_provider_keys(old, new)
    _move_memories(old, new)
    _move_defaults(old, new)
    connection = op.get_bind()
    for name in connection.execute(_TABLES).scalars():
        rows = sqlalchemy.table(name, sqlalchemy.column("application_id"))
        op.execute(
            sqlalchemy.update(rows)
            .where(rows.c.application_id == old)
            .values(application_id=new)
        )


def upgrade() -> None:
    _rename("pathfinder", "strategist")


def downgrade() -> None:
    _rename("strategist", "pathfinder")
