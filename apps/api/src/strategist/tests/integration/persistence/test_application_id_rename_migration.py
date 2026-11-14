from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from assistant_core.embeddings.embedder import EMBEDDING_DIMENSIONS
from psycopg.sql import SQL, Identifier
from pydantic import SecretStr
from testcontainers.community.postgres import PostgresContainer

from strategist.platform.config import get_settings
from strategist.platform.provider_key_cipher import ProviderKeyCipher, key_aad
from strategist.tests._support.provider_keys import sealed_provider_keys
from strategist.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    create_store_tables,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_13_0002"
REVISION = "2026_11_14_0001"
USER_ID = uuid4()
OWN_THREAD = uuid4()
OTHER_THREAD = uuid4()
KEY = "sk-proj-sentinel-0123456789WXYZ"
MEMORY_KEY = "kinome"


def _prefix(application: str) -> str:
    return f"app.{application}.user.{USER_ID}.knowledge"


def _cipher() -> ProviderKeyCipher:
    cipher = get_settings().provider_key_cipher
    assert cipher is not None
    return cipher


def _seed(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        for thread, application in (
            (OWN_THREAD, "pathfinder"),
            (OTHER_THREAD, "analytics"),
        ):
            connection.execute(
                "INSERT INTO conversations "
                "(id, user_id, site_id, name, assistant_id, application_id) "
                "VALUES (%s, %s, 'plasmodb', 'a thread', 'strategist', %s)",
                (str(thread), str(USER_ID), application),
            )
            connection.execute(
                "INSERT INTO gene_sets "
                "(id, user_id, site_id, name, gene_ids, source, step_count, "
                "application_id) "
                "VALUES (%s, %s, 'plasmodb', 'a set', '[]', 'paste', 1, %s)",
                (str(uuid4()), str(USER_ID), application),
            )
            connection.execute(
                "INSERT INTO user_provider_keys "
                "(id, user_id, application_id, provider, ciphertext, hint) "
                "VALUES (%s, %s, %s, 'openai', %s, 'WXYZ')",
                (
                    str(uuid4()),
                    str(USER_ID),
                    application,
                    _cipher().seal(
                        SecretStr(KEY), aad=key_aad(USER_ID, application, "openai")
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO store (prefix, key, value) VALUES (%s, %s, %s::jsonb)",
                (_prefix(application), MEMORY_KEY, '{"kind": "knowledge"}'),
            )
            connection.execute(
                "INSERT INTO store_vectors (prefix, key, field_name, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (
                    _prefix(application),
                    MEMORY_KEY,
                    "_embed_text",
                    "[" + ",".join(["0"] * EMBEDDING_DIMENSIONS) + "]",
                ),
            )


def _memory_prefixes(url: str) -> list[tuple[Any, ...]]:
    return rows(
        url,
        "SELECT s.prefix, v.prefix FROM store s "
        "JOIN store_vectors v ON v.prefix = s.prefix AND v.key = s.key "
        "ORDER BY s.prefix",
    )


def _defaults_naming(url: str, value: str) -> list[tuple[Any, ...]]:
    return rows(
        url,
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_default LIKE %s "
        "ORDER BY table_name, column_name",
        (f"'{value}'::%",),
    )


def _applications(url: str) -> list[tuple[Any, ...]]:
    return rows(
        url,
        "SELECT c.application_id, g.application_id FROM conversations c "
        "JOIN gene_sets g ON g.application_id = c.application_id "
        "ORDER BY c.application_id",
    )


def _opened_keys(url: str) -> list[tuple[str, str]]:
    stored = rows(
        url,
        "SELECT application_id, ciphertext FROM user_provider_keys "
        "ORDER BY application_id",
    )
    return [
        (
            application,
            _cipher()
            .open(bytes(blob), aad=key_aad(USER_ID, application, "openai"))
            .get_secret_value(),
        )
        for application, blob in stored
    ]


def _tables_naming(url: str, application: str) -> list[str]:
    tables = rows(
        url,
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name = 'application_id' AND table_schema = current_schema()",
    )
    return [
        table
        for (table,) in tables
        if rows(
            url,
            SQL("SELECT 1 FROM {} WHERE application_id = %s LIMIT 1").format(
                Identifier(table)
            ),
            (application,),
        )
    ]


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "strategist_test_application_id_rename"
    url = create_database(base_url, name)
    with sealed_provider_keys(monkeypatch):
        command.upgrade(alembic_config(url), PREVIOUS_REVISION)
        create_store_tables(url)
        _seed(url)
        yield url
    drop_database(base_url, name)


def test_the_upgrade_moves_every_row_of_the_application_to_strategist(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    assert _applications(seeded_database) == [
        ("analytics", "analytics"),
        ("strategist", "strategist"),
    ]
    assert _tables_naming(seeded_database, "pathfinder") == []
    assert _opened_keys(seeded_database) == [("analytics", KEY), ("strategist", KEY)]
    assert _memory_prefixes(seeded_database) == [
        (_prefix("analytics"), _prefix("analytics")),
        (_prefix("strategist"), _prefix("strategist")),
    ]
    assert _defaults_naming(seeded_database, "pathfinder") == []


def test_the_downgrade_restores_the_former_application(seeded_database: str) -> None:
    former_defaults = _defaults_naming(seeded_database, "pathfinder")
    command.upgrade(alembic_config(seeded_database), REVISION)
    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert _applications(seeded_database) == [
        ("analytics", "analytics"),
        ("pathfinder", "pathfinder"),
    ]
    assert _opened_keys(seeded_database) == [("analytics", KEY), ("pathfinder", KEY)]
    assert _memory_prefixes(seeded_database) == [
        (_prefix("analytics"), _prefix("analytics")),
        (_prefix("pathfinder"), _prefix("pathfinder")),
    ]
    assert former_defaults
    assert _defaults_naming(seeded_database, "pathfinder") == former_defaults
    assert _defaults_naming(seeded_database, "strategist") == []
