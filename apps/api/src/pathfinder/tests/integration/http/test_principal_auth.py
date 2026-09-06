"""Principal resolution: bearer identity, service-token application identity,
and the CSRF exemption a bearer earns.

The dependency is mounted on a route this module owns, so the assertions read
identity resolution and not any product endpoint.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any, cast
from uuid import UUID

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, Request, Response
from jwt.algorithms import ECAlgorithm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk.factory import get_site

from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.error_handlers import (
    app_error_handler,
    veupathdb_error_handler,
)
from pathfinder.platform.errors import AppError
from pathfinder.platform.principal import SERVICE_AUTH_HEADER, Principal
from pathfinder.platform.security import create_user_token
from pathfinder.tests.integration.http.conftest import make_user
from pathfinder.transport.http.deps import CurrentPrincipal

OAUTH_URL = "https://oauth.test"
JWKS_URL = f"{OAUTH_URL}/jwks"
SERVICE_SECRET = "analytics-service-secret-0123456789"
WDK_EMAIL = "researcher@example.org"

PRINCIPAL_PATH = "/principal"
CONVERSATIONS_PATH = "/api/v1/conversations"
STRATEGY_AST = {
    "recordType": "transcript",
    "root": {
        "id": "root",
        "searchName": "GenesByTaxon",
        "parameters": {"organism": {"type": "string", "value": "Plasmodium"}},
    },
}

_OK = 200
_CREATED = 201
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_UNAVAILABLE = 503


def _principal_app() -> FastAPI:
    """One route over the principal dependency, with the API's problem+json."""
    app = FastAPI()
    app.add_exception_handler(
        AppError,
        cast("Callable[[Request, Exception], Awaitable[Response]]", app_error_handler),
    )
    app.add_exception_handler(
        VEuPathDBError,
        cast(
            "Callable[[Request, Exception], Awaitable[Response]]",
            veupathdb_error_handler,
        ),
    )

    @app.get(PRINCIPAL_PATH, response_model=Principal)
    async def _read_principal(principal: CurrentPrincipal) -> Principal:
        return principal

    return app


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP521R1())


@pytest.fixture
def oauth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", OAUTH_URL)
    monkeypatch.setenv("PATHFINDER_SERVICE_TOKENS", f"analytics:{SERVICE_SECRET}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def principal_client(
    oauth_env: None,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """A client on the principal route, with no cookies and no CSRF header."""
    del oauth_env, patch_app_db_engine, db_cleaner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_principal_app()),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def bare_client(
    oauth_env: None,
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """A client on the real API, with no cookies and no CSRF header."""
    del oauth_env, patch_app_db_engine, db_cleaner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


def jwks_body(private_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    public = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {
        "keys": [
            {"kid": "0", "kty": "oct", "alg": "HS512", "k": "<your_client_secret>"},
            {
                "kid": "1",
                "use": "sig",
                "kty": "EC",
                "alg": "ES512",
                "crv": public["crv"],
                "x": public["x"],
                "y": public["y"],
            },
        ],
    }


def veupathdb_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    is_guest: bool = False,
) -> str:
    return jwt.encode(
        {
            "sub": "1248677203",
            "is_guest": is_guest,
            "aud": "apiComponentSite",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="ES512",
    )


def stub_oauth_and_wdk(
    respx_mock: respx.MockRouter,
    private_key: ec.EllipticCurvePrivateKey,
    *,
    email: str = WDK_EMAIL,
    is_guest: bool = False,
) -> respx.Route:
    """Stub the OAuth JWKS, the WDK session bootstrap, and the current-user lookup."""
    respx_mock.get(JWKS_URL).mock(
        return_value=httpx.Response(200, json=jwks_body(private_key)),
    )
    service_url = get_site(get_settings().veupathdb_default_site).service_url
    respx_mock.get(service_url.replace("/service", "/app")).mock(
        return_value=httpx.Response(200, text="ok"),
    )
    return respx_mock.get(f"{service_url}/users/current").mock(
        return_value=httpx.Response(
            200,
            json={"id": 1248677203, "isGuest": is_guest, "email": email},
        ),
    )


async def _user_ids_by_external_id(
    session_maker: async_sessionmaker[AsyncSession],
    external_id: str,
) -> list[UUID]:
    async with session_maker() as session:
        result = await session.execute(
            select(User.id).where(User.external_id == external_id),
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_a_veupathdb_bearer_token_authenticates_and_maps_to_a_user(
    principal_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        stub_oauth_and_wdk(respx_mock, signing_key)
        response = await principal_client.get(
            PRINCIPAL_PATH,
            headers={"Authorization": f"Bearer {veupathdb_token(signing_key)}"},
        )

    assert response.status_code == _OK, response.text
    body = response.json()
    assert body["credential"] == "veupathdb-bearer"
    assert body["applicationId"] == "pathfinder"
    assert await _user_ids_by_external_id(session_maker, WDK_EMAIL) == [
        UUID(body["userId"]),
    ]


@pytest.mark.asyncio
async def test_a_bearer_post_needs_no_csrf_header(
    bare_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        stub_oauth_and_wdk(respx_mock, signing_key)
        response = await bare_client.post(
            CONVERSATIONS_PATH,
            headers={"Authorization": f"Bearer {veupathdb_token(signing_key)}"},
            json={
                "siteId": "plasmodb",
                "name": "bearer chat",
                "strategyAst": STRATEGY_AST,
            },
        )

    assert response.status_code == _CREATED, response.text


@pytest.mark.asyncio
async def test_a_cookie_post_still_needs_the_csrf_header(
    bare_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await make_user(session)
    bare_client.cookies.set("pathfinder-auth", create_user_token(user.id))

    response = await bare_client.post(
        CONVERSATIONS_PATH,
        json={"siteId": "plasmodb", "name": "cookie chat", "strategyAst": STRATEGY_AST},
    )

    assert response.status_code == _FORBIDDEN, response.text
    assert response.json()["detail"] == "Missing required X-Requested-With header"


@pytest.mark.asyncio
async def test_an_invalid_bearer_never_falls_back_to_the_cookie(
    bare_client: httpx.AsyncClient,
    principal_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The CSRF exemption must not become a way in: a bad bearer is 401, not 2xx."""
    async with session_maker() as session:
        user = await make_user(session)
    cookie = create_user_token(user.id)
    bare_client.cookies.set("pathfinder-auth", cookie)
    principal_client.cookies.set("pathfinder-auth", cookie)

    with respx.mock(assert_all_called=False) as respx_mock:
        stub_oauth_and_wdk(respx_mock, signing_key)
        posted = await bare_client.post(
            CONVERSATIONS_PATH,
            headers={"Authorization": "Bearer garbage"},
            json={
                "siteId": "plasmodb",
                "name": "forged",
                "strategyAst": STRATEGY_AST,
            },
        )
        read = await principal_client.get(
            PRINCIPAL_PATH,
            headers={"Authorization": "Bearer garbage"},
        )

    assert posted.status_code == _UNAUTHORIZED, posted.text
    assert read.status_code == _UNAUTHORIZED, read.text


@pytest.mark.asyncio
async def test_an_unreachable_identity_provider_is_not_an_authentication_failure(
    principal_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(JWKS_URL).mock(return_value=httpx.Response(503, text="down"))
        response = await principal_client.get(
            PRINCIPAL_PATH,
            headers={"Authorization": f"Bearer {veupathdb_token(signing_key)}"},
        )

    assert response.status_code == _UNAVAILABLE, response.text
    assert "identity provider" in response.json()["title"]


@pytest.mark.asyncio
async def test_a_non_ascii_service_token_is_rejected(
    principal_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A header byte outside ASCII must be 401, not a 500 from the comparison."""
    async with session_maker() as session:
        user = await make_user(session)
    principal_client.cookies.set("pathfinder-auth", create_user_token(user.id))

    # The value goes out as raw bytes, which is the only way an 0x80-0xFF byte
    # reaches the server; Starlette decodes it as latin-1.
    response = await principal_client.get(
        PRINCIPAL_PATH,
        headers={
            SERVICE_AUTH_HEADER.encode(): b"caf\xe9-service-token-0123456789abcd",
        },
    )

    assert response.status_code == _UNAUTHORIZED, response.text


@pytest.mark.asyncio
async def test_a_guest_veupathdb_token_is_rejected(
    principal_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        stub_oauth_and_wdk(respx_mock, signing_key, is_guest=True)
        response = await principal_client.get(
            PRINCIPAL_PATH,
            headers={
                "Authorization": f"Bearer {veupathdb_token(signing_key, is_guest=True)}",
            },
        )

    assert response.status_code == _UNAUTHORIZED, response.text


@pytest.mark.asyncio
async def test_a_pathfinder_bearer_token_is_read_before_any_veupathdb_meaning(
    principal_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await make_user(session)

    with respx.mock(assert_all_called=False) as respx_mock:
        jwks = respx_mock.get(JWKS_URL).mock(return_value=httpx.Response(503))
        response = await principal_client.get(
            PRINCIPAL_PATH,
            headers={"Authorization": f"Bearer {create_user_token(user.id)}"},
        )

    assert response.status_code == _OK, response.text
    assert response.json()["credential"] == "pathfinder-bearer"
    assert response.json()["userId"] == str(user.id)
    assert jwks.call_count == 0


@pytest.mark.asyncio
async def test_a_cookie_names_the_cookie_credential(
    principal_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await make_user(session)
    principal_client.cookies.set("pathfinder-auth", create_user_token(user.id))

    response = await principal_client.get(PRINCIPAL_PATH)

    assert response.status_code == _OK, response.text
    assert response.json()["credential"] == "pathfinder-cookie"


@pytest.mark.asyncio
async def test_no_credential_is_unauthorized(
    principal_client: httpx.AsyncClient,
) -> None:
    response = await principal_client.get(PRINCIPAL_PATH)

    assert response.status_code == _UNAUTHORIZED, response.text


@pytest.mark.asyncio
async def test_a_service_token_names_the_calling_application(
    principal_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await make_user(session)
    principal_client.cookies.set("pathfinder-auth", create_user_token(user.id))

    response = await principal_client.get(
        PRINCIPAL_PATH,
        headers={SERVICE_AUTH_HEADER: SERVICE_SECRET},
    )

    assert response.status_code == _OK, response.text
    assert response.json()["applicationId"] == "analytics"


@pytest.mark.asyncio
async def test_an_unknown_service_token_is_rejected(
    principal_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await make_user(session)
    principal_client.cookies.set("pathfinder-auth", create_user_token(user.id))

    response = await principal_client.get(
        PRINCIPAL_PATH,
        headers={SERVICE_AUTH_HEADER: "not-the-configured-secret-0123456789"},
    )

    assert response.status_code == _UNAUTHORIZED, response.text


@pytest.mark.asyncio
async def test_the_wdk_lookup_is_reused_across_requests_with_one_token(
    principal_client: httpx.AsyncClient,
    signing_key: ec.EllipticCurvePrivateKey,
) -> None:
    token = veupathdb_token(signing_key)
    headers = {"Authorization": f"Bearer {token}"}

    with respx.mock(assert_all_called=False) as respx_mock:
        wdk = stub_oauth_and_wdk(respx_mock, signing_key)
        first = await principal_client.get(PRINCIPAL_PATH, headers=headers)
        second = await principal_client.get(PRINCIPAL_PATH, headers=headers)

    assert first.status_code == _OK, first.text
    assert second.status_code == _OK, second.text
    assert first.json()["userId"] == second.json()["userId"]
    assert wdk.call_count == 1
