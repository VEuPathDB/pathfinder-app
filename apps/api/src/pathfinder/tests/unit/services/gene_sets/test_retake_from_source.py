"""Re-taking a gene set from the strategy it came from.

A gene set holds the genes it was made from, so editing the source strategy
no longer changes it. Following the source again has to be something the user
asks for, on a set that has a source to follow.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.errors import ValidationError

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet, GeneSetSource

_OWNER = uuid4()
_STRATEGY_ID = 330531493


def _set(
    *,
    gene_ids: list[str] | None = None,
    source: GeneSetSource = "strategy",
    wdk_strategy_id: int | None = _STRATEGY_ID,
) -> GeneSet:
    return GeneSet(
        id="gs-1",
        user_id=_OWNER,
        site_id="plasmodb",
        name="ApiAP2 gametocyte",
        gene_ids=gene_ids or ["PF3D7_0100100", "PF3D7_0200200"],
        record_type="transcript",
        source=source,
        wdk_strategy_id=wdk_strategy_id,
        wdk_step_id=440107413,
        step_count=3,
    )


class _OneSetStore(GeneSetStore):
    """A store that answers one gene set and writes nothing."""

    def __init__(self, gene_set: GeneSet | None) -> None:
        super().__init__()
        self._gene_set = gene_set

    async def aget(self, entity_id: str) -> GeneSet | None:
        del entity_id
        return self._gene_set

    def save(self, entity: GeneSet) -> None:
        del entity


def _service(gs: GeneSet | None) -> GeneSetService:
    return GeneSetService(_OneSetStore(gs))


class TestASetWithASourceCanBeRetaken:
    @pytest.mark.asyncio
    async def test_the_membership_is_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = _service(_set())

        async def _resync(
            gene_set_id: str, *, wdk_strategy_id: int, site_id: str
        ) -> GeneSet | None:
            del gene_set_id, wdk_strategy_id, site_id
            return _set(gene_ids=["A"])

        monkeypatch.setattr(service, "resync_strategy", _resync)

        refreshed = await service.retake_from_source(_OWNER, "gs-1")

        assert refreshed.gene_ids == ["A"]

    @pytest.mark.asyncio
    async def test_it_follows_the_sets_own_strategy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gs = _set()
        service = _service(gs)
        followed: list[int] = []

        async def _resync(
            gene_set_id: str, *, wdk_strategy_id: int, site_id: str
        ) -> GeneSet | None:
            del gene_set_id, site_id
            followed.append(wdk_strategy_id)
            return gs

        monkeypatch.setattr(service, "resync_strategy", _resync)

        await service.retake_from_source(_OWNER, "gs-1")

        assert followed == [_STRATEGY_ID]


class TestASetWithNoSourceCannot:
    @pytest.mark.asyncio
    async def test_a_pasted_list_is_refused(self) -> None:
        service = _service(_set(wdk_strategy_id=None, source="paste"))

        with pytest.raises(ValidationError):
            await service.retake_from_source(_OWNER, "gs-1")

    @pytest.mark.asyncio
    async def test_the_refusal_says_there_is_no_source(self) -> None:
        service = _service(_set(wdk_strategy_id=None, source="paste"))

        with pytest.raises(ValidationError) as err:
            await service.retake_from_source(_OWNER, "gs-1")

        assert "strategy" in str(err.value.detail).lower()


class TestOwnershipStillApplies:
    @pytest.mark.asyncio
    async def test_another_users_set_is_not_found(self) -> None:
        service = _service(_set())

        with pytest.raises(NotFoundError):
            await service.retake_from_source(uuid4(), "gs-1")
