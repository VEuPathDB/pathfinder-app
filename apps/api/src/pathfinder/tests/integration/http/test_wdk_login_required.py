"""Every WDK-backed route refuses a request that names no registered VEuPathDB user.

VEuPathDB serves the WDK service to registered users only, so a request with no
token, or with a guest one, is answered before it reaches WDK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from assistant_core.memory.store import MemoryStore
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.wdk import get_site

from pathfinder.platform.config import get_settings
from pathfinder.services.users import get_or_create_user_id
from pathfinder.tests._support.veupathdb_tokens import (
    JWKS_URL,
    OAUTH_URL,
    jwks_body,
    make_signing_key,
    veupathdb_token,
)
from pathfinder.tests.integration.http._authz_matrix_owned import create_owned
from pathfinder.tests.integration.http._authz_matrix_support import Owned
from pathfinder.tests.integration.http.conftest import (
    WDK_AUTH_HEADER,
    chat_body,
    client_for,
)

_UNAUTHORIZED = 401
_NOT_FOUND = 404

LOGIN_TITLE = "VEuPathDB login required"
LOGIN_DETAIL = (
    "VEuPathDB serves registered users only, and this request "
    "carried no registered VEuPathDB token."
)
LOGIN_CODE = "WDK_LOGIN_REQUIRED"

TOKEN_ACCOUNT_EMAIL = "registered.account@example.org"


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return make_signing_key()


@pytest.fixture
def stubbed_oauth(
    monkeypatch: pytest.MonkeyPatch,
    signing_key: ec.EllipticCurvePrivateKey,
) -> Iterator[ec.EllipticCurvePrivateKey]:
    """Publish the test key where the app reads the OAuth signing key."""
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", OAUTH_URL)
    get_settings.cache_clear()
    service_url = get_site(get_settings().veupathdb_default_site).service_url
    with respx.mock(assert_all_called=False) as router:
        router.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json=jwks_body(signing_key)),
        )
        router.get(service_url.replace("/service", "/app")).mock(
            return_value=httpx.Response(200, text="ok"),
        )
        router.get(f"{service_url}/users/current").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1248677203, "isGuest": False, "email": TOKEN_ACCOUNT_EMAIL},
            ),
        )
        yield signing_key
    get_settings.cache_clear()


@pytest.fixture
async def owned(
    db_session: AsyncSession,
    app_memory_store: MemoryStore,
    patch_app_db_engine: None,
) -> Owned:
    del patch_app_db_engine
    return await create_owned(db_session, app_memory_store)


@pytest.fixture
async def signed_out(app: FastAPI, owned: Owned) -> AsyncIterator[httpx.AsyncClient]:
    """The owner of every resource, holding no VEuPathDB session."""
    async with client_for(app, owned.user_id) as client:
        yield client


@pytest.fixture
async def token_account_user_id(db_session: AsyncSession, owned: Owned) -> UUID:
    """The internal user the stubbed WDK account maps to.

    One session acts as one VEuPathDB account, so a request that passes the
    gate names this user and not another.
    """
    del owned
    user_id = await get_or_create_user_id(db_session, TOKEN_ACCOUNT_EMAIL)
    await db_session.commit()
    return user_id


def _assert_login_required(response: httpx.Response) -> None:
    assert response.status_code == _UNAUTHORIZED, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == LOGIN_CODE
    assert body["title"] == LOGIN_TITLE
    assert body["detail"] == LOGIN_DETAIL


class TestARequestWithNoVEuPathDBSessionIsRefused:
    async def test_chat_is_refused(
        self,
        signed_out: httpx.AsyncClient,
        owned: Owned,
    ) -> None:
        response = await signed_out.post(
            "/api/v1/chat", json=chat_body(owned.conversation_id)
        )

        _assert_login_required(response)

    async def test_a_gene_set_route_is_refused(
        self,
        signed_out: httpx.AsyncClient,
        owned: Owned,
    ) -> None:
        response = await signed_out.get(
            f"/api/v1/gene-sets/{owned.gene_set_ids[0]}/vdi-publication",
        )

        _assert_login_required(response)

    async def test_the_seed_route_is_refused(
        self,
        signed_out: httpx.AsyncClient,
    ) -> None:
        response = await signed_out.post("/api/v1/seed?siteId=plasmodb")

        _assert_login_required(response)

    async def test_the_own_datasets_listing_is_refused(
        self,
        signed_out: httpx.AsyncClient,
    ) -> None:
        response = await signed_out.get("/api/v1/eda/datasets?siteId=plasmodb")

        _assert_login_required(response)
        assert response.json()["code"] == LOGIN_CODE

    async def test_a_strategy_operation_is_refused(
        self,
        signed_out: httpx.AsyncClient,
        owned: Owned,
    ) -> None:
        response = await signed_out.post(
            f"/api/v1/conversations/{owned.conversation_id}/operations?siteId=plasmodb",
            json={"op": {"kind": "updateStrategyMeta", "name": "renamed"}},
        )

        _assert_login_required(response)


class TestAGuestVEuPathDBTokenIsNotALogin:
    async def test_a_guest_token_is_refused(
        self,
        app: FastAPI,
        owned: Owned,
        stubbed_oauth: ec.EllipticCurvePrivateKey,
    ) -> None:
        guest = veupathdb_token(stubbed_oauth, is_guest=True)
        async with client_for(app, owned.user_id) as client:
            client.headers[WDK_AUTH_HEADER] = guest
            response = await client.get(
                f"/api/v1/gene-sets/{owned.gene_set_ids[0]}/vdi-publication",
            )

        _assert_login_required(response)

    async def test_a_forged_token_is_refused(
        self,
        app: FastAPI,
        owned: Owned,
        stubbed_oauth: ec.EllipticCurvePrivateKey,
    ) -> None:
        del stubbed_oauth
        async with client_for(app, owned.user_id) as client:
            client.headers[WDK_AUTH_HEADER] = "not.a.token"
            response = await client.get(
                f"/api/v1/gene-sets/{owned.gene_set_ids[0]}/vdi-publication",
            )

        _assert_login_required(response)


class TestARegisteredTokenPassesTheGate:
    async def test_the_route_answers_its_own_404_instead(
        self,
        app: FastAPI,
        token_account_user_id: UUID,
        stubbed_oauth: ec.EllipticCurvePrivateKey,
    ) -> None:
        """A registered token reaches the handler, which then finds no such set."""
        registered = veupathdb_token(stubbed_oauth)
        async with client_for(app, token_account_user_id) as client:
            client.headers[WDK_AUTH_HEADER] = registered
            response = await client.get(
                f"/api/v1/gene-sets/{uuid4()}/vdi-publication",
            )

        assert response.status_code == _NOT_FOUND, response.text

    async def test_the_authorization_cookie_is_read_like_the_header(
        self,
        app: FastAPI,
        token_account_user_id: UUID,
        stubbed_oauth: ec.EllipticCurvePrivateKey,
    ) -> None:
        """A browser session carries the token as a cookie, not as a header."""
        registered = veupathdb_token(stubbed_oauth)
        async with client_for(app, token_account_user_id) as client:
            client.cookies.set("Authorization", registered)
            response = await client.get(
                f"/api/v1/gene-sets/{uuid4()}/vdi-publication",
            )

        assert response.status_code == _NOT_FOUND, response.text
