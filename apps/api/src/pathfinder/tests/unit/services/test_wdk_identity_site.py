"""The identity check reads the site the request names, not a fixed default.

The WDK user id is account scoped, so every site answers the same identity for
one token; a site whose catalog this process could not load answers nothing, so
the check reads a loaded site instead of waiting out the dead one's timeout.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.platform.errors import ErrorCode, SiteUnavailableError
from pathfinder.platform.principal import Principal
from pathfinder.platform.readiness import get_readiness, reset_readiness
from pathfinder.services import wdk_identity
from pathfinder.transport.http.deps import require_registered_wdk_identity

SESSION_USER = UUID("aa873910-0000-4000-8000-000000000001")
REGISTERED_TOKEN = "registered.veupathdb.token"


@pytest.fixture(autouse=True)
def _clean_state() -> Generator[None]:
    reset_readiness()
    reset = veupathdb_auth_token_ctx.set(None)
    yield
    veupathdb_auth_token_ctx.reset(reset)
    reset_readiness()


def _fake_wdk(
    monkeypatch: pytest.MonkeyPatch, *, email: str | None = "researcher@upenn.edu"
) -> list[str]:
    """Record the site every registered-email read names."""
    seen: list[str] = []

    async def registered_email(token: str, site_id: str) -> str | None:
        del token
        seen.append(site_id)
        return email

    monkeypatch.setattr(wdk_identity, "resolve_registered_email", registered_email)
    return seen


def _fake_user_row(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Map any email to one internal user without a database."""
    emails: list[str] = []

    async def _get_or_create(session: object, email: str) -> UUID:
        del session
        emails.append(email)
        return SESSION_USER

    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    monkeypatch.setattr(wdk_identity, "get_or_create_user_id", _get_or_create)
    monkeypatch.setattr(wdk_identity, "async_session_factory", _Session)
    return emails


class TestTheSiteAnIdentityCallReads:
    def test_a_loaded_site_answers_for_itself(self) -> None:
        get_readiness().mark_catalog_ready("plasmodb")

        assert wdk_identity.identity_site("plasmodb") == "plasmodb"

    def test_a_site_this_process_never_registered_answers_for_itself(self) -> None:
        assert wdk_identity.identity_site("plasmodb") == "plasmodb"

    def test_a_degraded_site_hands_the_call_to_a_loaded_one(self) -> None:
        readiness = get_readiness()
        readiness.mark_catalog_failed("veupathdb", TimeoutError())
        readiness.mark_catalog_ready("plasmodb")

        assert wdk_identity.identity_site("veupathdb") == "plasmodb"

    def test_a_degraded_site_with_no_loaded_peer_answers_for_itself(self) -> None:
        get_readiness().mark_catalog_failed("veupathdb", TimeoutError())

        assert wdk_identity.identity_site("veupathdb") == "veupathdb"


class TestOneTokenNamesOneUserOnEverySite:
    @pytest.mark.asyncio
    async def test_plasmodb_answers_the_same_user_as_the_portal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _fake_wdk(monkeypatch)
        _fake_user_row(monkeypatch)
        readiness = get_readiness()
        readiness.mark_catalog_ready("plasmodb")
        readiness.mark_catalog_ready("veupathdb")

        on_portal = await wdk_identity.resolve_veupathdb_user_id(
            REGISTERED_TOKEN, "veupathdb"
        )
        on_plasmodb = await wdk_identity.resolve_veupathdb_user_id(
            REGISTERED_TOKEN, "plasmodb"
        )

        assert on_portal == SESSION_USER
        assert on_plasmodb == SESSION_USER
        assert seen == ["veupathdb", "plasmodb"]

    @pytest.mark.asyncio
    async def test_a_degraded_default_is_never_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _fake_wdk(monkeypatch)
        _fake_user_row(monkeypatch)
        readiness = get_readiness()
        readiness.mark_catalog_failed("veupathdb", TimeoutError())
        readiness.mark_catalog_ready("plasmodb")

        assert (
            await wdk_identity.resolve_veupathdb_user_id(REGISTERED_TOKEN, "veupathdb")
            == SESSION_USER
        )
        assert seen == ["plasmodb"]


class TestAWdkOutageNamesNobody:
    @pytest.mark.asyncio
    async def test_the_session_keeps_its_own_identity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _fake_wdk(monkeypatch, email=None)
        _fake_user_row(monkeypatch)
        veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)
        session = Principal(user_id=SESSION_USER, credential="pathfinder-cookie")

        await wdk_identity.require_session_matches_wdk_identity(session, "plasmodb")

        assert (seen, session.user_id) == (["plasmodb"], SESSION_USER)


class TestTheRouteGateRefusesADegradedSiteBeforeAnyIdentityCall:
    @pytest.mark.asyncio
    async def test_the_named_degraded_site_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _fake_wdk(monkeypatch)
        get_readiness().mark_catalog_failed("veupathdb", TimeoutError())

        with pytest.raises(SiteUnavailableError) as refusal:
            await require_registered_wdk_identity(
                Principal(user_id=SESSION_USER, credential="pathfinder-cookie"),
                "veupathdb",
            )

        assert refusal.value.code == ErrorCode.SITE_UNAVAILABLE
        assert refusal.value.status == 503
        assert seen == []
