"""An identity read that the site does not answer refuses the request with a 503.

The read returns None only for a token the site refuses, so an outage is never
read as a sign-out and never lets the request through unchecked.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKError
from veupathdb.wdk import VEuPathDBClaims

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
    reset = veupathdb_auth_token_ctx.set(REGISTERED_TOKEN)
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _outage(status: int, cause: BaseException) -> WDKError:
    """The error the WDK client raises, chained to the failure that caused it."""
    error = WDKError("GET /users/current failed", status=status)
    error.__cause__ = cause
    return error


def _site_status(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "GET", "https://qa.plasmodb.org/plasmo.qa/service/users/current"
    )
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(str(status), request=request, response=response)


async def _raises(error: BaseException) -> str | None:
    raise error


async def _answers(value: str | None) -> str | None:
    return value


class TestTheMapping:
    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (_outage(502, TimeoutError()), "the site did not answer in time"),
            (
                _outage(502, httpx.ConnectError("refused")),
                "the site could not be reached",
            ),
            (_outage(503, _site_status(503)), "the site answered with an error"),
            (_outage(504, _site_status(504)), "the site answered with an error"),
        ],
    )
    async def test_a_site_that_does_not_answer_is_a_503(
        self, error: WDKError, reason: str
    ) -> None:
        with pytest.raises(SiteUnavailableError) as refusal:
            await wdk_identity.identity_or_unavailable("plasmodb", _raises(error))

        assert refusal.value.status == 503
        assert refusal.value.code == ErrorCode.SITE_UNAVAILABLE
        assert refusal.value.detail == f"Could not connect to plasmodb ({reason})."

    async def test_a_client_error_propagates_unchanged(self) -> None:
        error = WDKError("not found", status=404)

        with pytest.raises(WDKError) as raised:
            await wdk_identity.identity_or_unavailable("plasmodb", _raises(error))

        assert raised.value is error

    @pytest.mark.parametrize("value", ["researcher@upenn.edu", None])
    async def test_an_answer_passes_through(self, value: str | None) -> None:
        answer = await wdk_identity.identity_or_unavailable("plasmodb", _answers(value))

        assert answer == value


def _email_read_fails(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    async def registered_email(token: str, site_id: str) -> str | None:
        del token
        seen.append(site_id)
        raise _outage(502, TimeoutError())

    monkeypatch.setattr(wdk_identity, "resolve_registered_email", registered_email)
    return seen


class TestTheIdentityGate:
    async def test_the_user_id_read_refuses_on_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _email_read_fails(monkeypatch)

        with pytest.raises(SiteUnavailableError) as refusal:
            await wdk_identity.resolve_veupathdb_user_id(REGISTERED_TOKEN, "plasmodb")

        assert seen == ["plasmodb"]
        assert refusal.value.detail == (
            "Could not connect to plasmodb (the site did not answer in time)."
        )

    async def test_the_route_gate_refuses_on_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _validate(token: str, oauth_url: str) -> VEuPathDBClaims:
            del token, oauth_url
            return VEuPathDBClaims(sub="1216062453", is_guest=False)

        monkeypatch.setattr(wdk_identity, "validate_oauth_token", _validate)
        _email_read_fails(monkeypatch)

        with pytest.raises(SiteUnavailableError) as refusal:
            await require_registered_wdk_identity(
                Principal(user_id=SESSION_USER, credential="pathfinder-cookie"),
                "plasmodb",
            )

        assert refusal.value.status == 503
        assert refusal.value.code == ErrorCode.SITE_UNAVAILABLE


class TestASiteThatDoesNotAnswerHandsTheReadOn:
    async def test_a_loaded_peer_answers_when_the_named_site_times_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        readiness = get_readiness()
        readiness.mark_catalog_ready("plasmodb")
        readiness.mark_catalog_ready("toxodb")
        seen: list[str] = []

        async def registered_email(token: str, site_id: str) -> str | None:
            del token
            seen.append(site_id)
            if site_id == "plasmodb":
                raise _outage(502, TimeoutError())
            return "researcher@upenn.edu"

        monkeypatch.setattr(wdk_identity, "resolve_registered_email", registered_email)
        monkeypatch.setattr(wdk_identity, "get_or_create_user_id", _user_id_of)
        monkeypatch.setattr(wdk_identity, "async_session_factory", _NoSession)

        user_id = await wdk_identity.resolve_veupathdb_user_id(
            REGISTERED_TOKEN, "plasmodb"
        )

        assert (seen, user_id) == (["plasmodb", "toxodb"], SESSION_USER)

    async def test_the_last_sites_refusal_stands_when_none_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        readiness = get_readiness()
        readiness.mark_catalog_ready("plasmodb")
        readiness.mark_catalog_ready("toxodb")
        seen = _email_read_fails(monkeypatch)

        with pytest.raises(SiteUnavailableError) as refusal:
            await wdk_identity.resolve_veupathdb_user_id(REGISTERED_TOKEN, "plasmodb")

        assert seen == ["plasmodb", "toxodb"]
        assert refusal.value.detail == (
            "Could not connect to toxodb (the site did not answer in time)."
        )


async def _user_id_of(session: object, email: str) -> UUID:
    del session, email
    return SESSION_USER


class _NoSession:
    async def __aenter__(self) -> _NoSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> None:
        return None
