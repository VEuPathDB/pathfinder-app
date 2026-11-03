from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from sqlalchemy import text

from pathfinder.services.audit.sample_run import store_sample_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

_SECRET = "api_key=SECRET"
_UNREAD = (
    "the junction reads failed: HTTPStatusError Client error '404' for url "
    f"'https://qa.plasmodb.org/a?{_SECRET}'"
)
_ORTHOLOG = f"WDKError: GET /x?{_SECRET} -> HTTP 404: <html>body</html>"
_MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic/versions/2026_11_03_0002_old_audit_rows_hold_no_raw_error.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("old_audit_rows", _MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_a_stored_payload_is_clean_on_the_route_and_in_the_csv(
    app: FastAPI,
) -> None:
    user = (await seed_thread()).user_id
    stored = await store_sample_run(user)
    finding_id = stored.finding_ids[9]
    orthologs: dict[str, object] = {
        "named": None,
        "read": None,
        "compared": [],
        "forCorrected": None,
        "forAnnotated": None,
        "reason": _ORTHOLOG,
    }
    async with async_session_factory() as session:
        await session.execute(
            text(
                "UPDATE audit_evidence SET payload = jsonb_set(jsonb_set(payload, "
                "'{confirmation,result,evidenceUnread}', CAST(:unread AS jsonb)), "
                "'{confirmation,result,orthologs}', CAST(:orthologs AS jsonb)) "
                "WHERE finding_id = :finding AND kind = 'confirmation'"
            ),
            {
                "unread": json.dumps([_UNREAD]),
                "orthologs": json.dumps(orthologs),
                "finding": finding_id,
            },
        )
        await session.commit()
    detail = f"/api/v1/audits/{stored.run_id}/findings/{finding_id}"
    csv_route = f"/api/v1/audits/{stored.run_id}/findings.csv"
    async with client_for(app, user) as client:
        assert _SECRET in (await client.get(detail)).text
        assert _SECRET in (await client.get(csv_route)).text

    scrub = _migration().scrub_raw_text
    async with async_session_factory() as session:
        await session.run_sync(lambda sync: scrub(sync.connection()))
        await session.commit()

    async with client_for(app, user) as client:
        page = await client.get(detail)
        spreadsheet = await client.get(csv_route)
    assert page.status_code == 200
    assert _SECRET not in page.text
    assert _SECRET not in spreadsheet.text
    facts = page.json()["facts"]
    held = {fact["label"]: fact["value"] for group in facts for fact in group["facts"]}
    assert held["Evidence not read"] == "An internal error occurred"
    assert "Evidence not read: An internal error occurred" in spreadsheet.text
