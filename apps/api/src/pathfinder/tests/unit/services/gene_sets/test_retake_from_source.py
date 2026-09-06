"""Re-taking a gene set from the strategy it came from.

A gene set holds the genes it was made from, so editing the source strategy
no longer changes it. Following the source again has to be something the user
asks for, on a set that has a source to follow.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from veupathdb.errors import ValidationError

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.types import GeneSet

_OWNER = uuid4()


def _set(**over: Any) -> GeneSet:
    base: dict[str, Any] = {
        "id": "gs-1",
        "user_id": _OWNER,
        "site_id": "plasmodb",
        "name": "ApiAP2 gametocyte",
        "gene_ids": ["PF3D7_0100100", "PF3D7_0200200"],
        "record_type": "transcript",
        "source": "strategy",
        "wdk_strategy_id": 330531493,
        "wdk_step_id": 440107413,
        "step_count": 3,
    }
    base.update(over)
    return GeneSet(**base)


def _service(gs: GeneSet | None) -> tuple[GeneSetService, Any]:
    store = AsyncMock()
    store.aget = AsyncMock(return_value=gs)
    store.save = lambda value: None
    service = GeneSetService(store)
    return service, store


class TestASetWithASourceCanBeRetaken:
    @pytest.mark.asyncio
    async def test_the_membership_is_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _set()
        service, _ = _service(gs)
        monkeypatch.setattr(
            service, "resync_strategy", AsyncMock(return_value=_set(gene_ids=["A"]))
        )

        refreshed = await service.retake_from_source(gs.user_id, "gs-1")

        assert refreshed.gene_ids == ["A"]

    @pytest.mark.asyncio
    async def test_it_follows_the_sets_own_strategy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _set()
        service, _ = _service(gs)
        resync = AsyncMock(return_value=gs)
        monkeypatch.setattr(service, "resync_strategy", resync)

        await service.retake_from_source(gs.user_id, "gs-1")

        assert resync.await_args.kwargs["wdk_strategy_id"] == 330531493


class TestASetWithNoSourceCannot:
    @pytest.mark.asyncio
    async def test_a_pasted_list_is_refused(self) -> None:
        gs = _set(wdk_strategy_id=None, source="manual")
        service, _ = _service(gs)

        with pytest.raises(ValidationError):
            await service.retake_from_source(gs.user_id, "gs-1")

    @pytest.mark.asyncio
    async def test_the_refusal_says_there_is_no_source(self) -> None:
        gs = _set(wdk_strategy_id=None, source="manual")
        service, _ = _service(gs)

        with pytest.raises(ValidationError) as err:
            await service.retake_from_source(gs.user_id, "gs-1")

        assert "strategy" in str(err.value.detail).lower()


class TestOwnershipStillApplies:
    @pytest.mark.asyncio
    async def test_another_users_set_is_not_found(self) -> None:
        service, _ = _service(_set())

        with pytest.raises(NotFoundError):
            await service.retake_from_source(uuid4(), "gs-1")
