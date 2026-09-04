"""Control-sourcing helpers: validate IDs against WDK (split recognized vs
typo'd), and pull IDs from a saved gene set.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from pathfinder.services.experiment import control_sourcing
from pathfinder.services.experiment.control_sourcing import (
    control_ids_from_saved_gene_set,
    validate_control_ids,
)
from pathfinder.services.gene_lookup.result import GeneResult
from pathfinder.services.gene_lookup.wdk import GeneResolveResult


@pytest.mark.asyncio
async def test_validate_splits_recognized_from_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _resolve(
        site_id: str, gene_ids: list[str], **_kw: Any
    ) -> GeneResolveResult:
        # WDK recognizes g1 and g3 but not 'typo'.
        recognized = [g for g in gene_ids if g in {"g1", "g3"}]
        return GeneResolveResult(
            records=[GeneResult(gene_id=g) for g in recognized],
            total_count=len(recognized),
        )

    monkeypatch.setattr(control_sourcing, "resolve_gene_ids", _resolve)

    res = await validate_control_ids("plasmodb", ["g1", "typo", "g3", "g1"])
    assert res.valid_ids == ["g1", "g3"]
    assert res.unresolved_ids == ["typo"]


@pytest.mark.asyncio
async def test_validate_empty_skips_wdk(monkeypatch: pytest.MonkeyPatch) -> None:
    called = MagicMock()
    monkeypatch.setattr(control_sourcing, "resolve_gene_ids", called)
    res = await validate_control_ids("plasmodb", ["  ", ""])
    assert res.valid_ids == []
    assert res.unresolved_ids == []
    called.assert_not_called()


@pytest.mark.asyncio
async def test_control_ids_from_saved_gene_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gene_set = MagicMock()
    gene_set.gene_ids = ["g1", "g2", "g3"]
    service = MagicMock()
    service.get_for_user = AsyncMock(return_value=gene_set)
    monkeypatch.setattr(control_sourcing, "GeneSetService", lambda _store: service)
    monkeypatch.setattr(control_sourcing, "get_gene_set_store", MagicMock())

    ids = await control_ids_from_saved_gene_set(uuid4(), "gs_1")
    assert ids == ["g1", "g2", "g3"]
