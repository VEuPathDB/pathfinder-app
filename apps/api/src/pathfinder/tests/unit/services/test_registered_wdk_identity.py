"""A WDK-backed request must carry a registered VEuPathDB token."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import ExternalServiceError, WDKLoginRequiredError
from veupathdb.wdk import VEuPathDBClaims

from pathfinder.platform.errors import ErrorCode
from pathfinder.services import wdk_identity

REGISTERED_TOKEN = "registered.veupathdb.token"
GUEST_TOKEN = "guest.veupathdb.token"

_LOGIN_TITLE = "VEuPathDB login required"
_LOGIN_DETAIL = (
    "VEuPathDB serves registered users only, and this request "
    "carried no registered VEuPathDB token."
)


@pytest.fixture(autouse=True)
def _clear_request_token() -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _claims(monkeypatch: pytest.MonkeyPatch, *, is_guest: bool) -> list[str]:
    """Make every token read as this kind of user, and record the reads."""
    seen: list[str] = []

    async def _validate(token: str, oauth_url: str) -> VEuPathDBClaims:
        del oauth_url
        seen.append(token)
        return VEuPathDBClaims(sub="1248677203", is_guest=is_guest)

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _validate)
    return seen


class TestTheRequestMustNameARegisteredUser:
    @pytest.mark.asyncio
    async def test_a_request_without_a_token_is_refused(self) -> None:
        with pytest.raises(WDKLoginRequiredError) as raised:
            await wdk_identity.require_registered_wdk_login()

        assert raised.value.status == 401
        assert raised.value.code.value == ErrorCode.WDK_LOGIN_REQUIRED.value
        assert raised.value.title == _LOGIN_TITLE
        assert raised.value.detail == _LOGIN_DETAIL

    @pytest.mark.asyncio
    async def test_a_guest_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=True)
        veupathdb_auth_token_ctx.set(GUEST_TOKEN)

        with pytest.raises(WDKLoginRequiredError):
            await wdk_identity.require_registered_wdk_login()

    @pytest.mark.asyncio
    async def test_an_unverifiable_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _rejects(token: str, oauth_url: str) -> None:
            del token, oauth_url

        monkeypatch.setattr(wdk_identity, "validate_oauth_token", _rejects)
        veupathdb_auth_token_ctx.set("forged")

        with pytest.raises(WDKLoginRequiredError):
            await wdk_identity.require_registered_wdk_login()

    @pytest.mark.asyncio
    async def test_a_registered_token_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _claims(monkeypatch, is_guest=False)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        await wdk_identity.require_registered_wdk_login()

        assert seen == [REGISTERED_TOKEN]


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
