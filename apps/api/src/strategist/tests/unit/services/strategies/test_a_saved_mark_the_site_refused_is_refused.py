from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.errors import WDKError

from strategist.platform.errors import ErrorCode, SiteUnavailableError
from strategist.services.strategies import wdk_sync
from strategist.services.strategies.wdk_sync import set_the_saved_mark

_DOWN = WDKError("Service Unavailable", status=503)


class _Refusing:
    async def set_saved(self, strategy_id: int, *, is_saved: bool) -> NoReturn:
        del strategy_id, is_saved
        raise _DOWN


async def test_a_saved_mark_the_site_refused_refuses_the_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wdk_sync, "get_strategy_api", lambda _site: _Refusing())

    with pytest.raises(SiteUnavailableError) as refused:
        await set_the_saved_mark(site_id="plasmodb", wdk_strategy_id=9, is_saved=True)

    assert (refused.value.code, refused.value.detail) == (
        ErrorCode.SITE_UNAVAILABLE,
        (
            "Could not connect to plasmodb (the saved mark was not set: HTTP 503: "
            "VEuPathDB service error: Service Unavailable)."
        ),
    )
