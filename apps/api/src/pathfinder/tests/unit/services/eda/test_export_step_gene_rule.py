"""The tab's export clears the gene check the agent's export clears."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.eda import EdaAnalysisDetail, EdaFilter

from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.services.eda import gene_subset, steps
from pathfinder.services.eda.authoring import SubsetCount
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.gene_subset import NoGeneSubsetError
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    SAMPLE_ONLY_REFUSAL,
    analysis_detail,
    bound,
    de_study,
    gene_filter,
    sample_filter,
)


class _Refreshed(BaseModel):
    step_count: int


class _Conversations:
    """The commit seam, recording each operation it is asked to apply."""

    applied: ClassVar[list[AddLeafOp]] = []

    def __init__(self, session: AsyncSession) -> None:
        del session

    async def apply_operation(self, *_ids: object, **kwargs: Any) -> _Refreshed:
        self.applied.append(kwargs["op"])
        return _Refreshed(step_count=len(self.applied))


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    filters: Sequence[EdaFilter],
    *,
    with_computation: bool = False,
) -> list[AddLeafOp]:
    async def opened(*, conversation_id: object) -> tuple[Any, EdaAnalysisDetail]:
        del conversation_id
        detail = analysis_detail(with_computation=with_computation, filters=filters)
        return await bound(None), detail

    async def genes(
        _site: str, *, dataset_id: str, entity_id: str, filters: object
    ) -> SubsetCount:
        del dataset_id, filters
        return SubsetCount(entity_id=entity_id, count=3, unfiltered_count=5399)

    applied: list[AddLeafOp] = []
    monkeypatch.setattr(_Conversations, "applied", applied)
    monkeypatch.setattr(steps, "open_analysis_or_conflict", opened)
    monkeypatch.setattr(steps, "ConversationService", _Conversations)
    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", de_study)
    monkeypatch.setattr(gene_subset, "verified_count", genes)
    return applied


async def _export(thresholds: VolcanoThresholds | None = None) -> dict[str, Any]:
    return await steps.export_analysis_step(
        session=AsyncSession(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        thresholds=thresholds,
    )


async def test_a_sample_subset_with_no_computation_is_a_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = _wire(monkeypatch, [sample_filter()])

    with pytest.raises(NoGeneSubsetError) as refusal:
        await _export()

    assert refusal.value.status == 422
    assert refusal.value.detail == SAMPLE_ONLY_REFUSAL
    assert applied == []


async def test_a_gene_subset_is_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    applied = _wire(monkeypatch, [sample_filter(), gene_filter()])

    answer = await _export()

    assert answer == {"step_count": 1}
    assert [op.step.search_name for op in applied] == ["GenesByEdaSubset"]


async def test_a_computed_analysis_with_thresholds_is_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = _wire(monkeypatch, [sample_filter()], with_computation=True)

    await _export(
        VolcanoThresholds(effect_size_threshold=1.0, significance_threshold=0.05)
    )

    assert [op.step.search_name for op in applied] == ["GenesByEdaVizWithCompute"]
