from __future__ import annotations

import csv
import io

import pytest
from fastapi import FastAPI

from pathfinder.domain.audit.words import UNCHECKED_SENTENCES
from pathfinder.services.audit import export
from pathfinder.services.audit.export import HEADER
from pathfinder.services.audit.sample_run import store_sample_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)


async def test_the_sample_run_downloads_as_one_row_per_finding(app: FastAPI) -> None:
    user = (await seed_thread()).user_id
    stored = await store_sample_run(user)
    async with client_for(app, user) as client:
        response = await client.get(f"/api/v1/audits/{stored.run_id}/findings.csv")
        page = (
            await client.get(
                f"/api/v1/audits/{stored.run_id}/findings", params={"limit": 50}
            )
        ).json()
    rows = list(csv.reader(io.StringIO(response.text)))
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="audit-{stored.run_id}-findings.csv"'
    )
    assert rows[0] == HEADER
    assert len(rows) == 1 + len(page["findings"]) == 11
    assert [row[4] for row in rows[1:]] == [
        f["verdictText"] or UNCHECKED_SENTENCES[f["status"]] for f in page["findings"]
    ]
    assert [row[6] for row in rows[1:]] == [
        "Not reviewed" if f["reviewLine"] is None else f["reviewLine"]["verdictText"]
        for f in page["findings"]
    ]
    assert [row[10] for row in rows[1:]] == [
        ""
        if f["reviewLine"] is None or f["reviewLine"]["impact"] is None
        else str(f["reviewLine"]["impact"])
        for f in page["findings"]
    ]
    assert rows[1][5] == "0.5"
    assert rows[1][11].startswith("Sample fix: annotate PfNF54_100037200")
    assert rows[1][12].startswith("Reference coding sequence: 1,386 bases; ")
    assert [row[7] for row in rows[1:3]] == [
        "The review keeps the error",
        "The review keeps the error",
    ]


async def test_a_run_longer_than_one_page_downloads_whole(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(export, "EXPORT_PAGE", 3)
    user = (await seed_thread()).user_id
    stored = await store_sample_run(user)
    async with client_for(app, user) as client:
        response = await client.get(f"/api/v1/audits/{stored.run_id}/findings.csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert len(rows) == 11
    assert len({row[1] for row in rows[1:]}) == 10


async def test_another_persons_run_does_not_download(app: FastAPI) -> None:
    stored = await store_sample_run((await seed_thread()).user_id)
    stranger = (await seed_thread()).user_id
    async with client_for(app, stranger) as client:
        response = await client.get(f"/api/v1/audits/{stored.run_id}/findings.csv")
    assert response.status_code == 404
