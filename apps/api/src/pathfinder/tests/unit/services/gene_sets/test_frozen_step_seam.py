"""The name this application writes on the strategy that holds a frozen step."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pathfinder.platform.identity import GENE_SET_STRATEGY_NAME
from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet


async def test_the_holding_strategy_carries_this_products_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The library default names no product, so the caller names its own."""
    seen: list[tuple[str, list[str], str, str]] = []
    user_id = uuid4()
    gene_set = GeneSet(
        id="gs-1",
        user_id=user_id,
        name="Gametocyte markers",
        site_id="plasmodb",
        record_type="transcript",
        gene_ids=["PF3D7_0100100", "PF3D7_0200200"],
        source="manual",
    )

    async def _frozen(
        site_id: str,
        gene_ids: list[str],
        record_type: str,
        *,
        strategy_name: str,
    ) -> int | None:
        seen.append((site_id, gene_ids, record_type, strategy_name))
        return 55501

    async def _get_for_user(
        _self: GeneSetService, _user_id: UUID, _gene_set_id: str
    ) -> GeneSet:
        return gene_set

    monkeypatch.setattr(operations, "frozen_step_id", _frozen)
    monkeypatch.setattr(operations, "get_strategy_api", lambda _site_id: object())
    monkeypatch.setattr(GeneSetService, "get_for_user", _get_for_user)

    await GeneSetService(GeneSetStore()).get_step_results_service(user_id, "gs-1")

    assert seen == [
        (
            "plasmodb",
            ["PF3D7_0100100", "PF3D7_0200200"],
            "transcript",
            GENE_SET_STRATEGY_NAME,
        )
    ]
