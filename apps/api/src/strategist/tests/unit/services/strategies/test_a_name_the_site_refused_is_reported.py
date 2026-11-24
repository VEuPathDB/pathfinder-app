from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.errors import WDKError

from strategist.domain.unread import Unread
from strategist.services.strategies import naming
from strategist.services.strategies.naming import NamedThread, put_the_name_on_wdk

_DOWN = WDKError("Service Unavailable", status=503)


class _Refusing:
    async def update_strategy(self, strategy_id: int, *, name: str) -> NoReturn:
        del strategy_id, name
        raise _DOWN


async def test_a_name_the_site_refused_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(naming, "get_strategy_api", lambda _site: _Refusing())

    refused = await put_the_name_on_wdk(
        NamedThread(name="kinases", site_id="plasmodb", wdk_strategy_id=9)
    )

    assert refused == Unread(
        reason="HTTP 503: VEuPathDB service error: Service Unavailable"
    )
