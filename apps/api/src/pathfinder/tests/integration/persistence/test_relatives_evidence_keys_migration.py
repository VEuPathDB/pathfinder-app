from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.tests._support.audit import NF54
from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_10_23_0001"
REVISION = "2026_10_24_0002"
_KEYLESS: dict[str, Any] = {
    "kind": "relatives",
    "referenceGene": "REF",
    "referenceLength": 319,
    "modelLength": 110,
    "relativesMedian": 300.0,
}
_SIDED: dict[str, Any] = {
    **_KEYLESS,
    "side": "STRAIN_SHORT",
    "referenceOrganism": "Plasmodium falciparum 3D7",
}
_CONFIRMATION: dict[str, Any] = {"kind": "confirmation", "confirmation": {}}


def _finding(connection: psycopg.Connection[Any], run_id: str, gene: str) -> int:
    target = SingleGeneTarget(check="gene_length", genes=(gene,))
    found = connection.execute(
        "INSERT INTO audit_findings "
        "(run_id, check_name, genome, target, target_key, sampled, status) "
        "VALUES (%s, 'gene_length', %s, %s, %s, true, 'confirmed') RETURNING id",
        (
            run_id,
            NF54,
            json.dumps(target.model_dump(by_alias=True, mode="json")),
            target.key,
        ),
    ).fetchone()
    assert found is not None
    return int(found[0])


@pytest.fixture
def stored(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_relatives_evidence_keys"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    user_id, run_id = str(uuid4()), str(uuid4())
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        connection.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        connection.execute(
            "INSERT INTO audit_runs (id, user_id, site_id, scope, seed, stages) "
            "VALUES (%s, %s, 'plasmodb', '{}'::jsonb, 7, '{}'::jsonb)",
            (run_id, user_id),
        )
        for gene, kind, status, payload in (
            ("G1", "relatives", "stored", _KEYLESS),
            ("G2", "relatives", "stored", _SIDED),
            ("G3", "relatives", "failed", None),
            ("G4", "confirmation", "stored", _CONFIRMATION),
        ):
            connection.execute(
                "INSERT INTO audit_evidence (finding_id, kind, status, payload) "
                "VALUES (%s, %s, %s, %s)",
                (
                    _finding(connection, run_id, gene),
                    kind,
                    status,
                    None if payload is None else json.dumps(payload),
                ),
            )
    yield url
    drop_database(base_url, name)


def _payloads(url: str) -> list[Any]:
    return [
        row[0]
        for row in rows(
            url,
            "SELECT e.payload FROM audit_evidence e "
            "JOIN audit_findings f ON f.id = e.finding_id ORDER BY f.target_key",
        )
    ]


def test_stored_relatives_gain_the_keys_a_run_writes(stored: str) -> None:
    command.upgrade(alembic_config(stored), REVISION)
    keyless, sided, failed, confirmation = _payloads(stored)
    assert keyless == {
        **_KEYLESS,
        "relativeLengths": {},
        "relativesTier": None,
        "side": None,
        "referenceOrganism": None,
    }
    assert sided == {**_SIDED, "relativeLengths": {}, "relativesTier": None}
    assert (failed, confirmation) == (None, _CONFIRMATION)
    assert RelativesEvidence.model_validate(keyless).side is None
    assert RelativesEvidence.model_validate(sided).side == "STRAIN_SHORT"


def test_the_downgrade_drops_the_lengths_and_their_tier(stored: str) -> None:
    command.upgrade(alembic_config(stored), REVISION)
    command.downgrade(alembic_config(stored), PREVIOUS_REVISION)
    keyless, sided, failed, confirmation = _payloads(stored)
    assert keyless == {**_KEYLESS, "side": None, "referenceOrganism": None}
    assert sided == _SIDED
    assert (failed, confirmation) == (None, _CONFIRMATION)
