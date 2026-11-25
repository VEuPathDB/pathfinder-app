from __future__ import annotations

from typing import Any
from uuid import uuid4

from veupathdb.auth_context import veupathdb_auth_token_ctx

from strategist.jobs.job_context import TurnJobContext, TurnJobState
from strategist.services.search_waits import researcher_search_turn
from strategist.tests._support.holding_wdk import (
    TOKEN,
    HoldingWDK,
    holding_strategy_api,
)

_STRATEGY = 214681950
_READ = "GET /users/N/strategies/N"


class _Unheard:
    conversation_id = uuid4()
    turn_id = uuid4()

    async def write(self, chunk: dict[str, Any]) -> int:
        del chunk
        raise AssertionError


def _site() -> HoldingWDK:
    wdk = HoldingWDK()
    wdk.holds_the_strategy(
        {
            "strategyId": _STRATEGY,
            "name": "Kinases",
            "stepTree": {"stepId": 227385000},
            "steps": {
                "227385000": {
                    "searchName": "GenesByText",
                    "searchConfig": {"parameters": {}},
                }
            },
        }
    )
    return wdk


async def test_a_researchers_turn_reads_a_strategy_once() -> None:
    wdk = _site()
    api = holding_strategy_api(wdk)
    veupathdb_auth_token_ctx.set(TOKEN)

    with researcher_search_turn(_Unheard()):
        await api.get_strategy(_STRATEGY)
        await api.get_strategy(_STRATEGY)
    await api.get_strategy(_STRATEGY)

    assert wdk.sent[_READ] == 2


async def test_a_background_job_reads_the_strategy_each_time() -> None:
    wdk = _site()
    api = holding_strategy_api(wdk)
    state = TurnJobState.model_validate({"veupathdb_auth_token": TOKEN})

    async with TurnJobContext().restore(state):
        await api.get_strategy(_STRATEGY)
        await api.get_strategy(_STRATEGY)

    assert wdk.sent[_READ] == 2
