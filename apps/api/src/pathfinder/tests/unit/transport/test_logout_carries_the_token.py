"""Logging out sends the user's token, because WDK logs out whoever asked.

A request with no credential is answered as a guest, and WDK returns early for
a guest without touching anyone's session. The user is then told they are
logged out while their token still works.
"""

from __future__ import annotations

import httpx
import pytest
from veupathdb.wdk.auth_login import password_logout
from veupathdb_mcp.wdk import login

_TOKEN = "eyJhbGciOiJFUzUxMiJ9.real-user.sig"


class _Capture(httpx.AsyncBaseTransport):
    """Records the outbound logout request."""

    def __init__(self, status: int = 302) -> None:
        self.requests: list[httpx.Request] = []
        self._status = status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, headers={"location": "/"})


_REAL_CLIENT = httpx.AsyncClient


def _stub_client(monkeypatch: pytest.MonkeyPatch, capture: _Capture) -> _Capture:
    def _client(**kwargs: object) -> httpx.AsyncClient:
        del kwargs
        return _REAL_CLIENT(
            base_url="https://example.invalid/service", transport=capture
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return capture


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    return _stub_client(monkeypatch, _Capture())


class TestTheRequestCarriesTheCredential:
    @pytest.mark.asyncio
    async def test_the_token_is_sent_as_the_authorization_cookie(
        self, outbound: _Capture
    ) -> None:
        await password_logout("plasmodb", _TOKEN)

        cookie = outbound.requests[0].headers.get("cookie", "")
        assert f"Authorization={_TOKEN}" in cookie

    @pytest.mark.asyncio
    async def test_it_reaches_the_logout_endpoint(self, outbound: _Capture) -> None:
        await password_logout("plasmodb", _TOKEN)

        assert outbound.requests[0].url.path.endswith("/logout")

    @pytest.mark.asyncio
    async def test_a_redirect_counts_as_ended(self, outbound: _Capture) -> None:
        assert await password_logout("plasmodb", _TOKEN) is True


class TestARefusalIsReported:
    @pytest.mark.asyncio
    async def test_a_rejection_is_not_a_logout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_client(monkeypatch, _Capture(status=401))

        assert await password_logout("plasmodb", _TOKEN) is False


class TestTheServiceReportsWhatWDKDid:
    @pytest.mark.asyncio
    async def test_it_forwards_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, str]] = []

        async def _logout(site_id: str, token: str) -> bool:
            seen.append((site_id, token))
            return True

        monkeypatch.setattr(login, "password_logout", _logout)

        assert await login.end_veupathdb_session("plasmodb", _TOKEN) is True
        assert seen == [("plasmodb", _TOKEN)]

    @pytest.mark.asyncio
    async def test_without_a_token_wdk_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An uncredentialed logout is a guest logging a guest out, which WDK
        # answers with an early return.
        called = False

        async def _logout(site_id: str, token: str) -> bool:
            nonlocal called
            del site_id, token
            called = True
            return True

        monkeypatch.setattr(login, "password_logout", _logout)

        assert await login.end_veupathdb_session("plasmodb", None) is False
        assert called is False

    @pytest.mark.asyncio
    async def test_a_refusal_reaches_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _logout(site_id: str, token: str) -> bool:
            del site_id, token
            return False

        monkeypatch.setattr(login, "password_logout", _logout)

        assert await login.end_veupathdb_session("plasmodb", _TOKEN) is False
