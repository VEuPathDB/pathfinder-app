"""The own-datasets route through the whole application, VDI answered by recorded bodies."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import WDKError

from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.services.eda import catalog, private_datasets
from pathfinder.tests._support.recorded_vdi import (
    RecordedPermissions,
    RecordedVdi,
    permissions_body,
    vdi_body,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user

_INSTALLED = "4xZ5Q5pV1s4IM"
_URL = "/api/v1/eda/datasets?siteId=plasmodb"


@pytest.fixture(autouse=True)
def _fresh_readiness() -> Iterator[None]:
    reset_readiness()
    yield
    reset_readiness()


def _serve(monkeypatch: pytest.MonkeyPatch) -> RecordedVdi:
    rows = [row for row in vdi_body("datasets_owned") if row["datasetId"] == _INSTALLED]
    vdi = RecordedVdi(listing=rows)
    permissions = RecordedPermissions([permissions_body(with_user_study=True)])
    monkeypatch.setattr(private_datasets, "get_vdi_client", lambda _s: vdi.client())
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: permissions.client())
    return vdi


@pytest.mark.usefixtures("patch_app_db_engine", "signed_in_to_veupathdb")
async def test_the_listing_answers_with_the_installed_study_and_the_site_page(
    app: FastAPI, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch)
    user = await make_user(db_session)

    async with client_for(app, user.id, wdk_token="researcher.token") as client:
        response = await client.get(_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["uploadUrl"] == "https://plasmodb.org/plasmo/app/workspace/datasets"
    assert [
        (row["vdiId"], row["state"], row["datasetId"]) for row in body["datasets"]
    ] == [(_INSTALLED, "installed", f"EDAUD_{_INSTALLED}")]


@pytest.mark.usefixtures("patch_app_db_engine", "signed_in_to_veupathdb")
async def test_a_site_whose_catalog_failed_is_refused_before_vdi_is_read(
    app: FastAPI, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    vdi = _serve(monkeypatch)
    get_readiness().mark_catalog_failed("plasmodb", WDKError("refused", status=502))
    user = await make_user(db_session)

    async with client_for(app, user.id, wdk_token="researcher.token") as client:
        response = await client.get(_URL)

    assert response.status_code == 503
    assert response.json()["code"] == "SITE_UNAVAILABLE"
    assert vdi.calls() == []
