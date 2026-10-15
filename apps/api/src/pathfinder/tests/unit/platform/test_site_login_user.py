"""The website login of a request names its user once the token verifies
locally as registered."""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.security.http import HTTPAuthorizationCredentials
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import VEuPathDBClaims

from pathfinder.platform.config import get_settings
from pathfinder.platform.security import (
    create_user_token,
    site_login_user,
)
from pathfinder.services import wdk_identity

SITE_TOKEN = "site.login.token"
SITE_USER = UUID("cc873910-0000-4000-8000-000000000003")
REGISTERED = VEuPathDBClaims(sub="1216062453", is_guest=False)


@pytest.fixture(autouse=True)
def _site_token() -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(SITE_TOKEN)
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _validations(
    monkeypatch: pytest.MonkeyPatch, claims: VEuPathDBClaims | None
) -> list[str]:
    seen: list[str] = []

    async def _validate(token: str, oauth_url: str) -> VEuPathDBClaims | None:
        del oauth_url
        seen.append(token)
        return claims

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _validate)
    return seen


def _resolutions(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []

    async def _resolve(token: str, site_id: str) -> UUID | None:
        seen.append((token, site_id))
        return SITE_USER

    monkeypatch.setattr(wdk_identity, "resolve_veupathdb_user_id", _resolve)
    return seen


@pytest.mark.parametrize(
    "claims",
    [None, VEuPathDBClaims(sub="1216062453", is_guest=True)],
    ids=["invalid", "guest"],
)
async def test_a_token_that_is_not_a_registered_login_names_nobody_without_a_wdk_read(
    monkeypatch: pytest.MonkeyPatch, claims: VEuPathDBClaims | None
) -> None:
    _validations(monkeypatch, claims)
    resolved = _resolutions(monkeypatch)

    site_user = await site_login_user()

    assert site_user is None
    assert resolved == []


async def test_a_registered_token_names_the_user_its_account_maps_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _validations(monkeypatch, REGISTERED)
    resolved = _resolutions(monkeypatch)

    site_user = await site_login_user()

    assert site_user == SITE_USER
    assert resolved == [(SITE_TOKEN, get_settings().pathfinder_site)]


async def test_a_bearer_request_reads_no_site_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated = _validations(monkeypatch, REGISTERED)
    bearer = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=create_user_token(uuid4())
    )

    site_user = await site_login_user(bearer=bearer)

    assert site_user is None
    assert validated == []


async def test_a_request_with_no_site_login_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated = _validations(monkeypatch, REGISTERED)
    reset = veupathdb_auth_token_ctx.set(None)
    try:
        site_user = await site_login_user()
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert site_user is None
    assert validated == []
