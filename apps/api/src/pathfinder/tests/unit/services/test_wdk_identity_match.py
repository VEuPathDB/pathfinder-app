"""One PathFinder session acts on one VEuPathDB account.

The session cookie and the VEuPathDB token arrive independently, so the gate
checks that the token names the session's user before any WDK write.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk.auth_login import VEuPathDBClaims

from pathfinder.platform.errors import ErrorCode, WDKIdentityMismatchError
from pathfinder.platform.principal import CredentialKind, Principal
from pathfinder.services import wdk_identity
from pathfinder.transport.http.deps import require_registered_wdk_identity

SESSION_USER = UUID("aa873910-0000-4000-8000-000000000001")
OTHER_USER = UUID("bb873910-0000-4000-8000-000000000002")
REGISTERED_TOKEN = "registered.veupathdb.token"

_MISMATCH_TITLE = "VEuPathDB account changed"
_MISMATCH_DETAIL = (
    "Signed in to VEuPathDB as a different account than this PathFinder "
    "session. Sign in again."
)


@pytest.fixture(autouse=True)
def _clear_request_token() -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _session(credential: CredentialKind = "pathfinder-cookie") -> Principal:
    return Principal(user_id=SESSION_USER, credential=credential)


def _claims(monkeypatch: pytest.MonkeyPatch, *, is_guest: bool) -> None:
    async def _validate(token: str, oauth_url: str) -> VEuPathDBClaims:
        del token, oauth_url
        return VEuPathDBClaims(sub="1216062453", is_guest=is_guest)

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _validate)


def _token_names(monkeypatch: pytest.MonkeyPatch, user_id: UUID | None) -> list[str]:
    """Make the token resolve to ``user_id`` and record every lookup."""
    seen: list[str] = []

    async def _resolve(token: str, site_id: str) -> UUID | None:
        del site_id
        seen.append(token)
        return user_id

    monkeypatch.setattr(wdk_identity, "resolve_veupathdb_user_id", _resolve)
    return seen


class TestTheTokenMustNameTheSessionUser:
    @pytest.mark.asyncio
    async def test_another_account_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        with pytest.raises(WDKIdentityMismatchError) as raised:
            await wdk_identity.require_session_matches_wdk_identity(
                _session(), "plasmodb"
            )

        assert raised.value.status == 401
        assert raised.value.code == ErrorCode.WDK_IDENTITY_MISMATCH
        assert raised.value.title == _MISMATCH_TITLE
        assert raised.value.detail == _MISMATCH_DETAIL

    @pytest.mark.asyncio
    async def test_the_same_account_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _token_names(monkeypatch, SESSION_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert (
            await wdk_identity.require_session_matches_wdk_identity(
                _session(), "plasmodb"
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_a_request_without_a_token_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _token_names(monkeypatch, OTHER_USER)

        with pytest.raises(wdk_identity.WDKLoginRequiredError):
            await wdk_identity.require_session_matches_wdk_identity(
                _session(), "plasmodb"
            )

        assert seen == []

    @pytest.mark.asyncio
    async def test_an_unresolvable_token_does_not_sign_the_session_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WDK naming nobody is an outage, not a second account."""
        _token_names(monkeypatch, None)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert (
            await wdk_identity.require_session_matches_wdk_identity(
                _session(), "plasmodb"
            )
            is None
        )


class TestADevLoginSessionActsAsItsToken:
    """The dev-login route mints a synthetic user with no VEuPathDB identity."""

    @pytest.mark.asyncio
    async def test_the_mismatch_gate_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert (
            await wdk_identity.require_session_matches_wdk_identity(
                _session("dev-login"), "plasmodb"
            )
            is None
        )
        assert seen == []

    @pytest.mark.asyncio
    async def test_the_route_gate_still_requires_a_registered_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=True)
        _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set("guest.veupathdb.token")

        with pytest.raises(wdk_identity.WDKLoginRequiredError):
            await require_registered_wdk_identity(_session("dev-login"))

    @pytest.mark.asyncio
    async def test_the_route_gate_passes_with_another_accounts_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=False)
        _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert (
            await require_registered_wdk_identity(_session("dev-login")) == SESSION_USER
        )


class TestTheRouteGateRunsBothChecks:
    @pytest.mark.asyncio
    async def test_a_guest_token_is_a_login_refusal_not_a_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=True)
        seen = _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set("guest.veupathdb.token")

        with pytest.raises(wdk_identity.WDKLoginRequiredError):
            await require_registered_wdk_identity(_session())

        assert seen == []

    @pytest.mark.asyncio
    async def test_a_registered_token_for_another_account_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=False)
        _token_names(monkeypatch, OTHER_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        with pytest.raises(WDKIdentityMismatchError):
            await require_registered_wdk_identity(_session())

    @pytest.mark.asyncio
    async def test_a_registered_token_for_the_session_user_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claims(monkeypatch, is_guest=False)
        _token_names(monkeypatch, SESSION_USER)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)

        assert await require_registered_wdk_identity(_session()) == SESSION_USER
