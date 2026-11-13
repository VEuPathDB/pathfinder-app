"""add_procrastinate_schema

Revision ID: 3efc8ac5248a
Revises: 29b8e0c301b3
Create Date: 2026-04-14 13:52:38.389080

"""

from collections.abc import Sequence
from pathlib import Path

import psycopg
from alembic import op
from sqlalchemy.engine import make_url

# revision identifiers, used by Alembic.
revision: str = "3efc8ac5248a"
down_revision: str | Sequence[str] | None = "29b8e0c301b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The ``.sql`` file lives next to this migration so Alembic can load it
# verbatim. Docker deployment includes it via ``COPY apps/api/alembic
# apps/api/alembic`` in the Dockerfile, which copies every file under the
# ``alembic/`` tree — not just ``.py``. The hatch wheel (``[tool.hatch]
# packages = ["src/strategist"]``) does NOT include alembic artifacts, so
# if you ever switch from Docker deployment to wheel-based distribution,
# add ``include`` rules for the ``alembic/`` tree.
_SCHEMA_SQL = (Path(__file__).parent / "procrastinate_schema.sql").read_text()


def _apply_via_psycopg() -> None:
    """Run the multi-statement Procrastinate DDL via psycopg.

    The app's runtime engine is asyncpg (``postgresql+asyncpg://``) but the
    asyncpg driver rejects multi-statement SQL inside prepared statements.
    Procrastinate's DDL is a 600-line block of CREATE FUNCTION / CREATE
    TRIGGER statements, so we open a dedicated psycopg connection instead.
    """
    bind = op.get_bind()
    url = make_url(bind.engine.url)
    if url.drivername.startswith("postgresql+asyncpg"):
        psycopg_url = url.set(drivername="postgresql")
    else:
        psycopg_url = url
    conninfo = psycopg_url.render_as_string(hide_password=False)
    with (
        psycopg.connect(conninfo, autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(_SCHEMA_SQL)


def upgrade() -> None:
    """Apply the Procrastinate schema (tables, functions, triggers)."""
    _apply_via_psycopg()


def downgrade() -> None:
    """Drop all Procrastinate objects."""
    op.execute("DROP TABLE IF EXISTS procrastinate_events CASCADE")
    op.execute("DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE")
    op.execute("DROP TABLE IF EXISTS procrastinate_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS procrastinate_workers CASCADE")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_status CASCADE")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE")
