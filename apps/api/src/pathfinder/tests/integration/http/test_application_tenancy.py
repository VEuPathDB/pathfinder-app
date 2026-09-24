"""A resource one application holds is invisible to the same user elsewhere.

The mutating half of this property lives in the authorization matrix. These
cases cover the read half: the listings and the single-resource reads.
"""

from __future__ import annotations

import httpx
import pytest
from assistant_core.memory.store import MemoryStore
from assistant_core.platform.context import application_id_ctx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.control_sets import ControlSetService
from pathfinder.tests.integration.http._authz_matrix_owned import create_owned
from pathfinder.tests.integration.http._authz_matrix_support import Owned
from pathfinder.tests.integration.http.conftest import (
    client_for,
    make_user,
    other_application_client_for,
)

_OK = 200
_FORBIDDEN = 403
_NOT_FOUND = 404

SITE = "plasmodb"


@pytest.fixture
async def owned(db_session: AsyncSession, app_memory_store: MemoryStore) -> Owned:
    return await create_owned(db_session, app_memory_store)


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url)


async def test_the_conversation_list_holds_only_the_calling_application(
    app: FastAPI,
    patch_app_db_engine: None,
    owned: Owned,
    other_application: str,
) -> None:
    del patch_app_db_engine, other_application

    async with client_for(app, owned.user_id) as home:
        mine = await _get(home, "/api/v1/conversations")
    async with other_application_client_for(app, owned.user_id) as other:
        theirs = await _get(other, "/api/v1/conversations")

    assert [c["id"] for c in mine.json()] == [str(owned.conversation_id)]
    assert theirs.json() == []


async def test_one_conversation_is_refused_to_another_application_as_to_a_stranger(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    owned: Owned,
    other_application: str,
) -> None:
    """The refusal is whatever this route gives a non-owner, and no other."""
    del patch_app_db_engine, other_application
    url = f"/api/v1/conversations/{owned.conversation_id}"
    intruder = await make_user(db_session)

    async with client_for(app, owned.user_id) as home:
        mine = await _get(home, url)
    async with client_for(app, intruder.id) as stranger:
        theirs = await _get(stranger, url)
    async with other_application_client_for(app, owned.user_id) as other:
        elsewhere = await _get(other, url)

    assert mine.status_code == _OK, mine.text
    assert elsewhere.status_code in {_FORBIDDEN, _NOT_FOUND}, elsewhere.text
    assert elsewhere.status_code == theirs.status_code


async def test_the_gene_set_list_holds_only_the_calling_application(
    app: FastAPI,
    patch_app_db_engine: None,
    owned: Owned,
    other_application: str,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, other_application, signed_in_to_veupathdb

    async with client_for(app, owned.user_id) as home:
        mine = await _get(home, f"/api/v1/gene-sets?siteId={SITE}")
    async with other_application_client_for(app, owned.user_id) as other:
        theirs = await _get(other, f"/api/v1/gene-sets?siteId={SITE}")

    assert sorted(g["id"] for g in mine.json()) == sorted(owned.gene_set_ids)
    assert theirs.json() == []


async def test_a_control_set_list_holds_only_the_calling_application(
    db_session: AsyncSession,
    owned: Owned,
) -> None:
    service = ControlSetService(db_session)

    mine = await service.list_for_site(site_id=SITE, user_id=owned.user_id, tags=None)
    reset = application_id_ctx.set("another-application")
    try:
        theirs = await service.list_for_site(
            site_id=SITE, user_id=owned.user_id, tags=None
        )
    finally:
        application_id_ctx.reset(reset)

    assert [c.id for c in mine] == [str(owned.control_set_id)]
    assert theirs == []


async def test_the_memory_list_holds_only_the_calling_application(
    app: FastAPI,
    patch_app_db_engine: None,
    owned: Owned,
    other_application: str,
) -> None:
    del patch_app_db_engine, other_application

    async with client_for(app, owned.user_id) as home:
        mine = await _get(home, "/api/v1/memories")
    async with other_application_client_for(app, owned.user_id) as other:
        theirs = await _get(other, "/api/v1/memories")

    assert [m["key"] for m in mine.json()["knowledge"]] == [owned.memory_key]
    assert theirs.json()["knowledge"] == []
