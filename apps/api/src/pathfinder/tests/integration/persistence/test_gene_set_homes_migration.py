"""The gene homes of a saved set, applied to a real database.

A genomics site's set of genes holds that site's genes; a portal set, an
OrthoMCL set and a set of other records start with no homes.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    columns,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_12_0001"
REVISION = "2026_10_15_0001"
USER_ID = uuid4()
_SETS = [
    ("gs-plasmo", "plasmodb", ["PF3D7_1133400", "PF3D7_0709000"], "transcript"),
    ("gs-pasted", "toxodb", ["TGME49_200250"], None),
    ("gs-compounds", "plasmodb", ["CHEBI:15377"], "compound"),
    ("gs-portal", "veupathdb", ["PF3D7_1133400"], "transcript"),
    ("gs-ortho", "orthomcl", ["PF3D7_1133400.1-p1"], "sequence"),
]


def _seed_old_shape(url: str) -> None:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (str(USER_ID),))
        for set_id, site_id, genes, record_type in _SETS:
            connection.execute(
                "INSERT INTO gene_sets (id, user_id, application_id, site_id, name, "
                "gene_ids, source, step_count, record_type) "
                "VALUES (%s, %s, 'pathfinder', %s, %s, %s, 'paste', 1, %s)",
                (set_id, str(USER_ID), site_id, set_id, json.dumps(genes), record_type),
            )


@pytest.fixture
def seeded_database(
    database_url: str,
    postgres_container: PostgresContainer | None,
) -> Iterator[str]:
    """A database one revision back, holding a set from every kind of site."""
    del database_url, postgres_container

    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_gene_set_homes"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    _seed_old_shape(url)
    yield url
    drop_database(base_url, name)


def test_a_genomics_set_of_genes_holds_its_sites_genes(seeded_database: str) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    homes = dict(rows(seeded_database, "SELECT id, homes FROM gene_sets ORDER BY id"))

    assert homes == {
        "gs-compounds": {},
        "gs-ortho": {},
        "gs-pasted": {"TGME49_200250": {"geneId": "TGME49_200250", "siteId": "toxodb"}},
        "gs-plasmo": {
            "PF3D7_1133400": {"geneId": "PF3D7_1133400", "siteId": "plasmodb"},
            "PF3D7_0709000": {"geneId": "PF3D7_0709000", "siteId": "plasmodb"},
        },
        "gs-portal": {},
    }


def test_the_downgrade_removes_the_column_and_keeps_the_sets(
    seeded_database: str,
) -> None:
    command.upgrade(alembic_config(seeded_database), REVISION)

    command.downgrade(alembic_config(seeded_database), PREVIOUS_REVISION)

    assert "homes" not in columns(seeded_database, "gene_sets")
    assert len(rows(seeded_database, "SELECT id FROM gene_sets", ())) == len(_SETS)
