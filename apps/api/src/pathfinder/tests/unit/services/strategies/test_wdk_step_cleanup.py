from unittest.mock import AsyncMock, Mock

import pytest

from pathfinder.integrations.veupathdb.strategy_api import StrategyAPI
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.services.strategies.wdk_step_cleanup import (
    delete_orphaned_wdk_steps,
)


class _StubAPI:
    """Records the ids WDK was asked to delete, failing the named ones."""

    def __init__(self, fail_for: set[int] | None = None) -> None:
        self.deleted: list[int] = []
        self.fail_for: set[int] = fail_for or set()
        self.api = Mock(spec=StrategyAPI)
        self.api.delete_step = AsyncMock(side_effect=self._delete_step)

    async def _delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        if step_id in self.fail_for:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                title="boom",
                status=500,
            )
        self.deleted.append(step_id)


@pytest.mark.asyncio
async def test_no_ids_is_noop() -> None:
    api = _StubAPI()
    failed = await delete_orphaned_wdk_steps(api.api, [])
    assert failed == []
    assert api.deleted == []


@pytest.mark.asyncio
async def test_deletes_all_ids_in_parallel() -> None:
    api = _StubAPI()
    failed = await delete_orphaned_wdk_steps(api.api, [10, 20, 30])
    assert failed == []
    assert sorted(api.deleted) == [10, 20, 30]


@pytest.mark.asyncio
async def test_returns_ids_that_failed() -> None:
    api = _StubAPI(fail_for={20})
    failed = await delete_orphaned_wdk_steps(api.api, [10, 20, 30])
    assert failed == [20]
    assert sorted(api.deleted) == [10, 30]
