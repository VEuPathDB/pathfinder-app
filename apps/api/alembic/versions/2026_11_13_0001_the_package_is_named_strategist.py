from collections.abc import Sequence

import ormsgpack
import sqlalchemy
from alembic import op
from langgraph.checkpoint.serde.jsonplus import (
    EXT_CONSTRUCTOR_KW_ARGS,
    EXT_CONSTRUCTOR_POS_ARGS,
    EXT_CONSTRUCTOR_SINGLE_ARG,
    EXT_DELTA_SNAPSHOT,
    EXT_METHOD_SINGLE_ARG,
    EXT_PYDANTIC_V1,
    EXT_PYDANTIC_V2,
)

revision: str = "2026_11_13_0001"
down_revision: str | Sequence[str] | None = "2026_11_10_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPE_REFERENCES = frozenset(
    {
        EXT_CONSTRUCTOR_SINGLE_ARG,
        EXT_CONSTRUCTOR_POS_ARGS,
        EXT_CONSTRUCTOR_KW_ARGS,
        EXT_METHOD_SINGLE_ARG,
        EXT_PYDANTIC_V1,
        EXT_PYDANTIC_V2,
    }
)
_OPTION = ormsgpack.OPT_NON_STR_KEYS
_BATCH = 200
_KEYS = {
    "checkpoint_blobs": ("thread_id", "checkpoint_ns", "channel", "version"),
    "checkpoint_writes": (
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
    ),
}


def _module(module: str, old: str, new: str) -> str:
    if module == old or module.startswith(f"{old}."):
        return new + module[len(old) :]
    return module


def _decoded(blob: bytes, old: str, new: str) -> object:
    def hook(code: int, payload: bytes) -> ormsgpack.Ext:
        if code in _TYPE_REFERENCES:
            reference = ormsgpack.unpackb(payload, ext_hook=hook, option=_OPTION)
            reference[0] = _module(reference[0], old, new)
            return ormsgpack.Ext(code, ormsgpack.packb(reference, option=_OPTION))
        if code == EXT_DELTA_SNAPSHOT:
            value = ormsgpack.unpackb(payload, ext_hook=hook, option=_OPTION)
            return ormsgpack.Ext(code, ormsgpack.packb(value, option=_OPTION))
        return ormsgpack.Ext(code, payload)

    return ormsgpack.unpackb(blob, ext_hook=hook, option=_OPTION)


def renamed_package(blob: bytes, old: str, new: str) -> bytes:
    if old.encode() not in blob:
        return blob
    return ormsgpack.packb(_decoded(blob, old, new), option=_OPTION)


def _table(name: str, key: tuple[str, ...]) -> sqlalchemy.Table:
    return sqlalchemy.Table(
        name,
        sqlalchemy.MetaData(),
        *(sqlalchemy.Column(column) for column in key),
        sqlalchemy.Column("type", sqlalchemy.Text),
        sqlalchemy.Column("blob", sqlalchemy.LargeBinary),
    )


def _rename_rows(
    connection: sqlalchemy.Connection, table: sqlalchemy.Table, old: str, new: str
) -> None:
    key = [column for column in table.columns if column.name not in {"type", "blob"}]
    holds_the_name = sqlalchemy.func.position(
        sqlalchemy.literal(old.encode(), sqlalchemy.LargeBinary).op("IN")(table.c.blob)
    )
    after: tuple[object, ...] | None = None
    while True:
        query = (
            sqlalchemy.select(*key, table.c.blob)
            .where(table.c.type == "msgpack", holds_the_name > 0)
            .order_by(*key)
            .limit(_BATCH)
        )
        if after is not None:
            query = query.where(sqlalchemy.tuple_(*key) > sqlalchemy.tuple_(*after))
        batch = connection.execute(query).all()
        if not batch:
            return
        for row in batch:
            blob = bytes(row.blob)
            renamed = renamed_package(blob, old, new)
            if renamed != blob:
                connection.execute(
                    sqlalchemy.update(table)
                    .where(*(column == row._mapping[column.name] for column in key))
                    .values(blob=renamed)
                )
        after = tuple(batch[-1])[: len(key)]


def _rename(old: str, new: str) -> None:
    connection = op.get_bind()
    present = set(sqlalchemy.inspect(connection).get_table_names())
    for name, key in _KEYS.items():
        if name in present:
            _rename_rows(connection, _table(name, key), old, new)


def upgrade() -> None:
    _rename("pathfinder", "strategist")


def downgrade() -> None:
    _rename("strategist", "pathfinder")
