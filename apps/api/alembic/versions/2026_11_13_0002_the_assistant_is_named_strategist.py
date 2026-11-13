from collections.abc import Sequence

import sqlalchemy
from alembic import op

revision: str = "2026_11_13_0002"
down_revision: str | Sequence[str] | None = "2026_11_13_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = (
    "UPDATE conversations SET assistant_id = :new WHERE assistant_id = :old",
    "UPDATE eval_staged_cases SET assistant_id = :new WHERE assistant_id = :old",
    (
        "UPDATE eval_staged_cases SET extract = jsonb_set(extract, "
        "'{assistantId}', to_jsonb(CAST(:new AS text))) "
        "WHERE extract ->> 'assistantId' = :old"
    ),
    (
        "UPDATE procrastinate_jobs SET args = jsonb_set(args, "
        "'{payload,assistant_id}', to_jsonb(CAST(:new AS text))) "
        "WHERE args #>> '{payload,assistant_id}' = :old"
    ),
    (
        "UPDATE procrastinate_jobs SET args = jsonb_set(args, "
        "'{payload,body,assistantId}', to_jsonb(CAST(:new AS text))) "
        "WHERE args #>> '{payload,body,assistantId}' = :old"
    ),
)


def _rename(old: str, new: str) -> None:
    for statement in _RENAMES:
        op.execute(sqlalchemy.text(statement).bindparams(old=old, new=new))


def upgrade() -> None:
    _rename("pathfinder", "strategist")


def downgrade() -> None:
    _rename("strategist", "pathfinder")
