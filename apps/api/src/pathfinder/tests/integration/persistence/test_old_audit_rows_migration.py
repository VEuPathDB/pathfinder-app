from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from pathfinder.persistence.repositories.audit import STOPPED_MESSAGE
from pathfinder.services.audit.units import NOT_READ
from pathfinder.tests.integration.persistence._migration_db import (
    alembic_config,
    create_database,
    drop_database,
    psycopg_url,
    rows,
)

PREVIOUS_REVISION = "2026_11_03_0001"
REVISION = "2026_11_03_0002"
_GENERIC = "An internal error occurred"
_SECRET = "api_key=held-in-the-query"
_RAW = f"Bad gateway for https://qa.plasmodb.org/answer?{_SECRET}"
_RAW_SQL = "(ProgrammingError)\nSELECT token\nFROM audit_runs"
_RAW_REASON = f"the audit job failed: HTTPStatusError: {_RAW}"
_CLEAN_REASON = f"the audit job failed: HTTPStatusError: {_GENERIC}"
_WRITTEN = "plasmodb serves no gene row for PF3D7_X"
_STAGE_NOTE = f"NF54: failed ({_RAW})"
_WRITTEN_NOTE = "2 candidates in 1 genome, 1 sampled"
_WIRE = "WDKError: POST /record-types/gene/records -> HTTP 404: <html>body</html>"
_REFUSED_WORDS = "VEuPathDB service error: the organism is unknown"
_VERDICT = "GAP: the absent genome holds an assembly gap there"
_DECLINED = "PF3D7_X names no gene of plasmodb"
_WRITTEN_GONE = "BUSCO scores failed: gone; genome provenance failed: gone"
_UNREAD_TEXT = f"the junction reads failed: HTTPStatusError Client error for url {_RAW}"
_KEPT_UNREAD = "the junction reads failed: the site answered 503"


def _stages(**fields: str | None) -> str:
    return json.dumps(
        {
            "stages": [
                {"name": "collect", "finished": False, "message": _STAGE_NOTE},
                {"name": "screen", "finished": False, "message": _WRITTEN_NOTE},
            ],
            "halted": None,
            "targetFailure": None,
            **fields,
        }
    )


class _Seed:
    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self.connection = connection
        self.user_id = str(uuid4())
        connection.execute("INSERT INTO users (id) VALUES (%s)", (self.user_id,))
        self.keys = 0

    def run(self, **fields: str | None) -> str:
        run_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO audit_runs (id, user_id, site_id, scope, seed, stages) "
            "VALUES (%s, %s, 'plasmodb', '{}'::jsonb, 7, %s)",
            (run_id, self.user_id, _stages(**fields)),
        )
        return run_id

    def genome(self, run_id: str, status: str, message: str | None) -> None:
        self.keys += 1
        self.connection.execute(
            "INSERT INTO audit_genomes (run_id, organism, role, status, message) "
            "VALUES (%s, %s, 'audited', %s, %s)",
            (run_id, f"organism {self.keys}", status, message),
        )

    def finding(self, run_id: str, status: str, message: str | None) -> int:
        self.keys += 1
        found = self.connection.execute(
            "INSERT INTO audit_findings (run_id, check_name, genome, target, "
            "target_key, sampled, status, message) "
            "VALUES (%s, 'gene_length', 'g', '{}'::jsonb, %s, true, %s, %s) "
            "RETURNING id",
            (run_id, f"key {self.keys}", status, message),
        ).fetchone()
        assert found is not None
        finding_id = found[0]
        assert isinstance(finding_id, int)
        return finding_id

    def payload(self, finding_id: int, payload: dict[str, object]) -> None:
        self.connection.execute(
            "INSERT INTO audit_evidence (finding_id, kind, status, payload) "
            "VALUES (%s, 'confirmation', 'stored', %s)",
            (finding_id, json.dumps(payload)),
        )

    def evidence(self, finding_id: int, kind: str, status: str, message: str) -> None:
        self.connection.execute(
            "INSERT INTO audit_evidence (finding_id, kind, status, message) "
            "VALUES (%s, %s, %s, %s)",
            (finding_id, kind, status, message),
        )


@pytest.fixture
def database(
    database_url: str, postgres_container: PostgresContainer | None
) -> Iterator[str]:
    del database_url, postgres_container
    base_url = os.environ["DATABASE_URL"]
    name = "pathfinder_test_old_audit_rows"
    url = create_database(base_url, name)
    command.upgrade(alembic_config(url), PREVIOUS_REVISION)
    yield url
    drop_database(base_url, name)


def _seeded(url: str) -> dict[str, str]:
    with psycopg.connect(psycopg_url(url), autocommit=True) as connection:
        seed = _Seed(connection)
        raw = seed.run(halted=_RAW_REASON)
        multi_line = seed.run(halted=f"the audit job failed: KeyError: {_RAW_SQL}")
        signed_out = seed.run(halted="sign-in needed")
        targets = seed.run(targetFailure=_RAW)
        seed.genome(raw, "trying", _RAW_REASON)
        seed.genome(raw, "failed", _RAW)
        finding = seed.finding(raw, "trying", _RAW_REASON)
        stopped = seed.finding(raw, "failed", f"{STOPPED_MESSAGE}; {_RAW_REASON}")
        failed = seed.finding(raw, "failed", _RAW)
        written = seed.finding(raw, "failed", _WRITTEN)
        unreached = seed.finding(raw, "unreached", _RAW)
        unread = seed.finding(raw, "unread", NOT_READ)
        unread_raw = seed.finding(raw, "unread", _RAW)
        wire = seed.finding(raw, "failed", _WIRE)
        said = seed.finding(raw, "failed", _REFUSED_WORDS)
        parsing = seed.finding(raw, "failed", "Data parsing failed: Unexpected row")
        written_gone = seed.finding(raw, "failed", _WRITTEN_GONE)
        busco = seed.finding(
            raw,
            "failed",
            f"BUSCO scores failed: {_RAW}; genome provenance failed: gone",
        )
        stopped_raw = seed.finding(raw, "failed", f"{STOPPED_MESSAGE}; {_RAW}")
        trailing = seed.finding(raw, "failed", f"{_RAW}; body continues")
        seed.payload(
            failed,
            {
                "kind": "confirmation",
                "confirmation": {
                    "check": "intron_support",
                    "result": {
                        "evidenceUnread": [_UNREAD_TEXT, _KEPT_UNREAD],
                        "correctionReason": _WIRE,
                        "orthologs": {"reason": _REFUSED_WORDS},
                        "gene": "KEPT_GENE",
                    },
                },
            },
        )
        confirmed_raw = seed.finding(raw, "confirmed", _RAW)
        declined_raw = seed.finding(raw, "declined", _WIRE)
        screened_raw = seed.finding(raw, "screened", _RAW)
        confirmed_said = seed.finding(raw, "confirmed", _VERDICT)
        declined_said = seed.finding(raw, "declined", _DECLINED)
        seed.genome(raw, "collected", f"BUSCO scores failed: {_RAW}")
        seed.genome(raw, "unread", _RAW)
        placed = seed.finding(targets, "unreached", _RAW)
        seed.evidence(finding, "relatives", "trying", _RAW_REASON)
        seed.evidence(failed, "gene_evidence", "failed", _RAW)
        seed.evidence(failed, "relatives", "unread", _RAW)
        return {
            "raw": raw,
            "multi_line": multi_line,
            "signed_out": signed_out,
            "targets": targets,
            "finding": str(finding),
            "stopped": str(stopped),
            "failed": str(failed),
            "written": str(written),
            "unreached": str(unreached),
            "unread": str(unread),
            "unread_raw": str(unread_raw),
            "wire": str(wire),
            "said": str(said),
            "parsing": str(parsing),
            "written_gone": str(written_gone),
            "busco": str(busco),
            "stopped_raw": str(stopped_raw),
            "trailing": str(trailing),
            "payload_finding": str(failed),
            "confirmed_raw": str(confirmed_raw),
            "declined_raw": str(declined_raw),
            "screened_raw": str(screened_raw),
            "confirmed_said": str(confirmed_said),
            "declined_said": str(declined_said),
            "placed": str(placed),
        }


def _run_field(url: str, run_id: str, field: str) -> object:
    ((value,),) = rows(
        url, "SELECT stages->>%s FROM audit_runs WHERE id = %s", (field, run_id)
    )
    return value


def _finding_message(url: str, finding_id: str) -> object:
    ((value,),) = rows(
        url, "SELECT message FROM audit_findings WHERE id = %s", (finding_id,)
    )
    return value


def _snapshot(url: str) -> list[tuple[object, ...]]:
    held = []
    for query in (
        "SELECT id::text, stages::text FROM audit_runs ORDER BY id",
        "SELECT organism, status, message FROM audit_genomes ORDER BY organism",
        "SELECT id, status, message FROM audit_findings ORDER BY id",
        "SELECT finding_id, kind, status, message FROM audit_evidence ORDER BY 1, 2",
    ):
        held.extend(rows(url, query))
    return held


def test_a_reason_the_failed_job_wrote_keeps_its_type_and_loses_its_text(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    assert _run_field(database, ids["raw"], "halted") == _CLEAN_REASON
    assert _run_field(database, ids["multi_line"], "halted") == (
        f"the audit job failed: KeyError: {_GENERIC}"
    )
    assert _run_field(database, ids["signed_out"], "halted") == "sign-in needed"
    assert _finding_message(database, ids["finding"]) == _CLEAN_REASON
    assert _finding_message(database, ids["stopped"]) == (
        f"{STOPPED_MESSAGE}; {_CLEAN_REASON}"
    )
    assert rows(
        database, "SELECT message FROM audit_genomes WHERE status = 'trying'"
    ) == [(_CLEAN_REASON,)]
    assert rows(
        database, "SELECT message FROM audit_evidence WHERE status = 'trying'"
    ) == [(_CLEAN_REASON,)]


def test_a_target_failure_and_the_findings_that_repeat_it_are_cleaned(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    assert _run_field(database, ids["targets"], "targetFailure") == _GENERIC
    assert _finding_message(database, ids["placed"]) == _GENERIC
    assert _run_field(database, ids["raw"], "targetFailure") is None


def test_a_failed_or_unreached_row_holding_an_address_or_a_wire_line_is_cleaned(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    assert _finding_message(database, ids["failed"]) == _GENERIC
    assert _finding_message(database, ids["unreached"]) == _GENERIC
    assert _finding_message(database, ids["wire"]) == _GENERIC
    assert rows(
        database, "SELECT message FROM audit_genomes WHERE status = 'failed'"
    ) == [(_GENERIC,)]
    assert rows(
        database, "SELECT message FROM audit_evidence WHERE status = 'failed'"
    ) == [(_GENERIC,)]


def test_a_stage_note_holding_an_address_is_cleaned_and_a_written_one_is_kept(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    ((notes,),) = rows(
        database,
        "SELECT jsonb_agg(stage->>'message') "
        "FROM audit_runs, jsonb_array_elements(stages->'stages') AS stage "
        "WHERE id = %s",
        (ids["raw"],),
    )
    assert notes == [f"NF54: failed ({_GENERIC})", _WRITTEN_NOTE]
    ((names,),) = rows(
        database,
        "SELECT jsonb_agg(stage->>'name') "
        "FROM audit_runs, jsonb_array_elements(stages->'stages') AS stage "
        "WHERE id = %s",
        (ids["raw"],),
    )
    assert names == ["collect", "screen"]


def test_a_row_of_any_status_holding_an_address_or_a_wire_line_is_cleaned(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    for held in ("unread_raw", "confirmed_raw", "declined_raw", "screened_raw"):
        assert _finding_message(database, ids[held]) == _GENERIC
    assert rows(
        database,
        "SELECT message FROM audit_genomes WHERE status IN ('collected', 'unread') "
        "ORDER BY status",
    ) == [(f"BUSCO scores failed: {_GENERIC}",), (_GENERIC,)]
    assert rows(
        database, "SELECT message FROM audit_evidence WHERE status = 'unread'"
    ) == [(_GENERIC,)]


def test_text_the_code_treats_as_raw_is_cleaned_and_written_parts_kept(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    assert _finding_message(database, ids["said"]) == _GENERIC
    assert _finding_message(database, ids["parsing"]) == _GENERIC
    assert _finding_message(database, ids["busco"]) == (
        f"BUSCO scores failed: {_GENERIC}; genome provenance failed: gone"
    )
    assert _finding_message(database, ids["stopped_raw"]) == (
        f"{STOPPED_MESSAGE}; {_GENERIC}"
    )
    assert _finding_message(database, ids["trailing"]) == _GENERIC


def test_the_text_a_stored_payload_carries_is_cleaned(database: str) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    ((result,),) = rows(
        database,
        "SELECT payload->'confirmation'->'result' FROM audit_evidence "
        "WHERE finding_id = %s AND kind = 'confirmation'",
        (ids["payload_finding"],),
    )
    assert result == {
        "evidenceUnread": [_GENERIC, _KEPT_UNREAD],
        "correctionReason": _GENERIC,
        "orthologs": {"reason": _GENERIC},
        "gene": "KEPT_GENE",
    }


def test_a_sentence_we_wrote_is_left_alone_in_any_status(
    database: str,
) -> None:
    ids = _seeded(database)
    command.upgrade(alembic_config(database), REVISION)
    assert _finding_message(database, ids["written"]) == _WRITTEN
    assert _finding_message(database, ids["unread"]) == NOT_READ
    assert _finding_message(database, ids["written_gone"]) == _WRITTEN_GONE
    assert _finding_message(database, ids["confirmed_said"]) == _VERDICT
    assert _finding_message(database, ids["declined_said"]) == _DECLINED


def test_a_second_run_of_the_migration_changes_nothing(database: str) -> None:
    _seeded(database)
    config = alembic_config(database)
    command.upgrade(config, REVISION)
    once = _snapshot(database)
    command.downgrade(config, PREVIOUS_REVISION)
    assert _snapshot(database) == once
    command.upgrade(config, REVISION)
    assert _snapshot(database) == once
