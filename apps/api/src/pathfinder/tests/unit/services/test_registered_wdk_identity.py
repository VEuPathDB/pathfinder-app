"""A WDK-backed request must carry a registered VEuPathDB token."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import ExternalServiceError
from veupathdb.wdk.auth_login import VEuPathDBClaims

from pathfinder.platform.errors import ErrorCode
from pathfinder.services import wdk_identity

REGISTERED_TOKEN = "registered.veupathdb.token"
GUEST_TOKEN = "guest.veupathdb.token"

_LOGIN_TITLE = "VEuPathDB login required"
_LOGIN_DETAIL = "Sign in to VEuPathDB to use searches, strategies and gene sets."


@pytest.fixture(autouse=True)
def _clear_request_token() -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _claims(monkeypatch: pytest.MonkeyPatch, *, is_guest: bool) -> None:
    async def _validate(token: str, oauth_url: str) -> VEuPathDBClaims:
        del token, oauth_url
        return VEuPathDBClaims(sub="1248677203", is_guest=is_guest)

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _validate)


class TestTheRequestMustNameARegisteredUser:
    @pytest.mark.asyncio
    async def test_a_request_without_a_token_is_refused(self) -> None:
        with pytest.raises(wdk_identity.WDKLoginRequiredError) as raised:
            await wdk_identity.require_registered_wdk_login()

        assert raised.value.status == 401
        assert raised.value.code == ErrorCode.WDK_LOGIN_REQUIRED
        assert raised.value.title == _LOGIN_TITLE
        assert raised.value.detail == _LOGIN_DETAIL

    @pytest.mark.asyncio
    async def test_a_guest_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=True)
        veupathdb_auth_token_ctx.set(GUEST_TOKEN)

        with pytest.raises(wdk_identity.WDKLoginRequiredError):
            await wdk_identity.require_registered_wdk_login()

    @pytest.mark.asyncio
    async def test_an_unverifiable_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _rejects(token: str, oauth_url: str) -> None:
            del token, oauth_url

        monkeypatch.setattr(wdk_identity, "validate_oauth_token", _rejects)
        veupathdb_auth_token_ctx.set("forged")

        with pytest.raises(wdk_identity.WDKLoginRequiredError):
            await wdk_identity.require_registered_wdk_login()

    @pytest.mark.asyncio
    async def test_a_registered_token_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=False)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert await wdk_identity.require_registered_wdk_login() is None


class TestAnUnreadableKeyIsNotABadToken:
    @pytest.mark.asyncio
    async def test_the_identity_provider_failure_travels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key that cannot be read is 503, not a refusal of the credential."""

        async def _unavailable(token: str, oauth_url: str) -> VEuPathDBClaims:
            del token, oauth_url
            raise ExternalServiceError(
                service="VEuPathDB identity provider",
                detail="cannot be read",
                status=503,
            )

        monkeypatch.setattr(wdk_identity, "validate_oauth_token", _unavailable)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        with pytest.raises(ExternalServiceError) as raised:
            await wdk_identity.require_registered_wdk_login()

        assert raised.value.status == 503


class TestTheServiceAccountIsNotTheSignedInUser:
    @pytest.mark.asyncio
    async def test_no_request_token_reads_no_wdk_user(self) -> None:
        """Without a request token there is no session to report."""
        assert await wdk_identity.fetch_wdk_user("plasmodb") is None
