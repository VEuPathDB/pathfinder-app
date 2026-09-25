"""The own-datasets listing reads VDI as the researcher, never as the deployment."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.config import get_settings
from pathfinder.platform.error_handlers import veupathdb_error_handler
from pathfinder.services.eda import catalog, private_datasets
from pathfinder.tests._support.recorded_vdi import (
    RecordedPermissions,
    RecordedVdi,
    permissions_body,
    vdi_body,
)
from pathfinder.transport.http.deps import (
    get_current_user_with_db_row,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.routers import eda_datasets

_Handler = Callable[[Request, Exception], Awaitable[Response]]
_RESEARCHER = "researcher.token"
_SERVICE = "service.account.token"
_FAILED = "MoZ5BBpM8U0IM"


@pytest.fixture(autouse=True)
def service_token(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("VEUPATHDB_AUTH_TOKEN", _SERVICE)
    get_settings.cache_clear()
    assert get_settings().veupathdb_auth_token == _SERVICE
    yield
    get_settings.cache_clear()


def _app(monkeypatch: pytest.MonkeyPatch, vdi: RecordedVdi) -> FastAPI:
    permissions = RecordedPermissions([permissions_body(with_user_study=True)])

    async def _user() -> UUID:
        return uuid4()

    monkeypatch.setattr(private_datasets, "get_vdi_client", lambda _s: vdi.client())
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: permissions.client())
    app = FastAPI()
    app.include_router(eda_datasets.router)
    app.add_exception_handler(VEuPathDBError, cast("_Handler", veupathdb_error_handler))
    app.dependency_overrides[get_current_user_with_db_row] = _user
    app.dependency_overrides[require_registered_wdk_identity] = _user
    return app


async def _list(app: FastAPI) -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/eda/datasets?siteId=plasmodb")
    return response.status_code


async def test_the_listing_and_a_failed_rows_read_carry_the_researchers_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vdi = RecordedVdi(statuses={_FAILED: [vdi_body("rnaseqrc_import_invalid")]})
    handle = veupathdb_auth_token_ctx.set(_RESEARCHER)
    try:
        status = await _list(_app(monkeypatch, vdi))
    finally:
        veupathdb_auth_token_ctx.reset(handle)

    assert status == 200
    sent = [
        (call, request.headers["authorization"])
        for call, request in zip(vdi.calls(), vdi.requests, strict=True)
    ]
    assert ("GET /datasets", f"Bearer {_RESEARCHER}") in sent
    assert (f"GET /datasets/{_FAILED}", f"Bearer {_RESEARCHER}") in sent
    assert {bearer for _call, bearer in sent} == {f"Bearer {_RESEARCHER}"}


async def test_with_no_request_token_no_vdi_call_is_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deployment's token is set and the researcher's is absent: VDI hears nothing."""
    vdi = RecordedVdi()

    status = await _list(_app(monkeypatch, vdi))

    assert status == 401
    assert vdi.calls() == []
