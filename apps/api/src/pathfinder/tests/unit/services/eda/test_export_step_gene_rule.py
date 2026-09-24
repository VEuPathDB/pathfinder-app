"""The tab's export clears the gene check the agent's export clears."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.eda import EdaAnalysisDetail, EdaFilter

from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.operations import AddLeafOp
from pathfinder.domain.strategy.operations.types import GraphOperation
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda import steps
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.gene_subset import NoGeneSubsetError
from pathfinder.tests._support.eda_doubles import no_gene_study
from pathfinder.tests._support.eda_step_doubles import (
    DE_DATASET,
    DE_GENES,
    SAMPLE_ONLY_REFUSAL,
    StudyReader,
    binding_of,
    de_analysis,
    de_study,
    gene_filter,
    sample_filter,
    wire_gene_count,
)
from pathfinder.tests._support.step_params import string_param


class _Refreshed(BaseModel):
    step_count: int


class _Conversations:
    """The commit seam, recording each operation it is asked to apply."""

    applied: ClassVar[list[GraphOperation]] = []
    kinds: ClassVar[list[dict[str, StampedKind]]] = []

    def __init__(self, session: AsyncSession) -> None:
        del session

    async def apply_operation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        site_id: str,
        op: GraphOperation,
        analysis_kinds: Mapping[str, StampedKind] | None = None,
    ) -> _Refreshed:
        del conversation_id, user_id
        assert site_id == "plasmodb"
        self.applied.append(op)
        self.kinds.append(dict(analysis_kinds or {}))
        return _Refreshed(step_count=len(self.applied))


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    filters: Sequence[EdaFilter],
    *,
    with_computation: bool = False,
    study: StudyReader = de_study,
) -> list[GraphOperation]:
    detail = de_analysis(filters=filters, with_computation=with_computation)

    async def opened(*, conversation_id: object) -> tuple[Any, EdaAnalysisDetail]:
        del conversation_id
        return binding_of(detail), detail

    applied: list[GraphOperation] = []
    monkeypatch.setattr(_Conversations, "applied", applied)
    monkeypatch.setattr(_Conversations, "kinds", [])
    monkeypatch.setattr(steps, "open_analysis_or_conflict", opened)
    monkeypatch.setattr(steps, "ConversationService", _Conversations)
    wire_gene_count(monkeypatch, study=study, genes=DE_GENES)
    return applied


def _leaves(applied: list[GraphOperation]) -> list[AddLeafOp]:
    leaves = [op for op in applied if isinstance(op, AddLeafOp)]
    assert len(leaves) == len(applied)
    return leaves


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


async def test_a_study_with_no_gene_entity_is_a_422_and_writes_no_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = _wire(monkeypatch, [sample_filter()], study=no_gene_study)

    with pytest.raises(NoGeneSubsetError) as refusal:
        await _export()

    assert refusal.value.status == 422
    assert refusal.value.detail == (
        "This study has no single gene variable, so it cannot export genes as "
        "a step. Nothing was written."
    )
    assert applied == []


async def test_a_gene_subset_is_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    applied = _wire(monkeypatch, [sample_filter(), gene_filter()])

    answer = await _export()

    assert answer == {"step_count": 1}
    leaves = _leaves(applied)
    assert [leaf.step.search_name for leaf in leaves] == ["GenesByEdaSubset"]
    assert string_param(leaves[0].step, "eda_dataset_id") == DE_DATASET
    assert _Conversations.kinds == [
        {
            leaves[0].step.id: StampedKind(
                search_name="GenesByEdaSubset", kind=AnalysisKind.SUBSET
            )
        }
    ]


async def test_a_computed_analysis_with_thresholds_is_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = _wire(monkeypatch, [sample_filter()], with_computation=True)

    await _export(
        VolcanoThresholds(effect_size_threshold=1.0, significance_threshold=0.05)
    )

    leaves = _leaves(applied)
    assert [leaf.step.search_name for leaf in leaves] == ["GenesByEdaVizWithCompute"]
    assert _Conversations.kinds == [
        {
            leaves[0].step.id: StampedKind(
                search_name="GenesByEdaVizWithCompute", kind=AnalysisKind.COMPUTE
            )
        }
    ]
