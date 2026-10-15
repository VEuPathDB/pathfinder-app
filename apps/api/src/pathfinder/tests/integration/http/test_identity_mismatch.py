"""A PathFinder bearer and a VEuPathDB token that name two accounts are refused.

A bearer and a VEuPathDB token arrive independently, so the WDK gate refuses
them when they disagree. A browser has no PathFinder credential of its own: its
website login names the one account it acts as.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from assistant_core.persistence.models import Conversation
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.wdk import get_site

from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.veupathdb_tokens import (
    JWKS_URL,
    OAUTH_URL,
    SUBJECT,
    current_user_by_token,
    jwks_body,
    make_signing_key,
    veupathdb_token,
)
from pathfinder.tests.integration.http.conftest import (
    WDK_AUTH_HEADER,
    bearer_client_for,
    chat_body,
    chat_jobs,
    make_user,
)

_OK = 200
_UNAUTHORIZED = 401
_NOT_FOUND = 404

OTHER_ACCOUNT_EMAIL = "other.account@example.org"
OTHER_ACCOUNT_SUBJECT = "1216062453"
SIGNED_IN_ACCOUNT_EMAIL = "signed.in.account@example.org"
SITE_ID = "plasmodb"
CONVERSATIONS_PATH = "/api/v1/conversations"

MISMATCH_CODE = "WDK_IDENTITY_MISMATCH"
MISMATCH_TITLE = "VEuPathDB account changed"
MISMATCH_DETAIL = (
    "Signed in to VEuPathDB as a different account than this PathFinder "
    "session. Sign in again."
)


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return make_signing_key()


@pytest.fixture
def another_veupathdb_account(
    monkeypatch: pytest.MonkeyPatch,
    signing_key: ec.EllipticCurvePrivateKey,
) -> Iterator[str]:
    """A verifiable token whose WDK account is not the session's user.

    The site names the signed-in account for a token of ``SUBJECT``.
    """
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", OAUTH_URL)
    get_settings.cache_clear()
    with respx.mock(assert_all_called=False) as router:
        router.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json=jwks_body(signing_key)),
        )
        for site_id in (get_settings().pathfinder_site, SITE_ID):
            service_url = get_site(site_id).service_url
            router.get(service_url.replace("/service", "/app")).mock(
                return_value=httpx.Response(200, text="ok"),
            )
            router.get(f"{service_url}/users/current").mock(
                side_effect=current_user_by_token(
                    signing_key,
                    {
                        SUBJECT: SIGNED_IN_ACCOUNT_EMAIL,
                        OTHER_ACCOUNT_SUBJECT: OTHER_ACCOUNT_EMAIL,
                    },
                ),
            )
        yield veupathdb_token(signing_key, subject=OTHER_ACCOUNT_SUBJECT)
    get_settings.cache_clear()


@pytest.fixture
async def session_user_id(
    db_session: AsyncSession,
    patch_app_db_engine: None,
) -> UUID:
    del patch_app_db_engine
    user = await make_user(db_session)
    return user.id


@pytest.fixture
async def conversation_id(db_session: AsyncSession, session_user_id: UUID) -> UUID:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=session_user_id,
        site_id=SITE_ID,
        name="kinases",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.commit()
    return conversation.id


@pytest.fixture
async def mismatched(
    app: FastAPI,
    session_user_id: UUID,
    another_veupathdb_account: str,
) -> AsyncIterator[httpx.AsyncClient]:
    """A bearer of one user, carrying another account's VEuPathDB token.

    A bearer names no website login, so the WDK gate is what refuses it.
    """
    async with bearer_client_for(app, session_user_id) as client:
        client.headers[WDK_AUTH_HEADER] = another_veupathdb_account
        yield client


def _assert_identity_mismatch(response: httpx.Response) -> None:
    assert response.status_code == _UNAUTHORIZED, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == MISMATCH_CODE
    assert body["title"] == MISMATCH_TITLE
    assert body["detail"] == MISMATCH_DETAIL


class TestARouteRefusesTheSecondAccount:
    async def test_a_gene_set_route_is_refused(
        self,
        mismatched: httpx.AsyncClient,
    ) -> None:
        response = await mismatched.get(
            f"/api/v1/gene-sets/{uuid4()}/vdi-publication",
        )

        _assert_identity_mismatch(response)


class TestNoTurnIsDispatchedForTheSecondAccount:
    async def test_chat_is_refused_and_defers_no_job(
        self,
        mismatched: httpx.AsyncClient,
        conversation_id: UUID,
        in_memory_jobs: InMemoryConnector,
    ) -> None:
        response = await mismatched.post(
            "/api/v1/chat", json=chat_body(conversation_id)
        )

        _assert_identity_mismatch(response)
        assert chat_jobs(in_memory_jobs) == []


class TestAWebsiteLoginActsAsItsOwnAccount:
    async def test_another_accounts_login_does_not_see_the_first_users_work(
        self,
        app: FastAPI,
        conversation_id: UUID,
        another_veupathdb_account: str,
    ) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Requested-With": "XMLHttpRequest"},
            cookies={"Authorization": another_veupathdb_account},
        ) as client:
            response = await client.get(CONVERSATIONS_PATH, params={"siteId": SITE_ID})

        assert response.status_code == _OK, response.text
        assert str(conversation_id) not in response.text
