"""An evaluation of a gene set records the membership it scored.

The run is the only writer of an experiment record, so every path that
evaluates a saved set records what that set held at the time.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pathfinder.services.experiment import service
from pathfinder.services.experiment._deserialize import experiment_from_json
from pathfinder.services.experiment.metrics import (
    evaluate_gene_ids_against_controls,
)
from pathfinder.services.experiment.service import run_experiment, shared
from pathfinder.services.experiment.service.phases import evaluate, validate
from pathfinder.services.experiment.types import experiment_to_json
from pathfinder.services.experiment.types.experiment import ExperimentConfig
from pathfinder.services.gene_sets.types import GeneSet, GeneSetMembership

_SET_ID = "gs-gametocyte-secreted"
_SET_GENES = ["PF3D7_0100100", "PF3D7_0200200", "PF3D7_0304600"]


def _config(*, gene_set_id: str | None) -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByRNASeq",
        parameters={},
        positive_controls=["PF3D7_0100100"],
        negative_controls=["PF3D7_0930300"],
        controls_search_name="GenesByGeneList",
        controls_param_name="ds_gene_ids",
        gene_set_id=gene_set_id,
    )


def _controls() -> Any:
    return evaluate_gene_ids_against_controls(
        gene_ids=_SET_GENES,
        positive_controls=["PF3D7_0100100"],
        negative_controls=["PF3D7_0930300"],
    )


class _SetStore:
    """Answers one gene set and refuses every other id."""

    def __init__(self, gene_set: GeneSet | None) -> None:
        self._gene_set = gene_set
        self.asked: list[str] = []

    async def aget(self, entity_id: str) -> GeneSet | None:
        self.asked.append(entity_id)
        return self._gene_set


def _gene_set(gene_ids: list[str]) -> GeneSet:
    return GeneSet(
        id=_SET_ID,
        user_id=uuid4(),
        site_id="plasmodb",
        name="gametocyte secreted",
        gene_ids=gene_ids,
        source="strategy",
    )


def _install(monkeypatch: pytest.MonkeyPatch, store: _SetStore) -> None:
    monkeypatch.setattr(
        evaluate, "run_single_step_controls", AsyncMock(return_value=_controls())
    )
    monkeypatch.setattr(
        evaluate, "_persist_experiment_strategy", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        shared, "extract_and_hydrate_genes", AsyncMock(return_value=([], [], [], []))
    )
    monkeypatch.setattr(validate, "phase_robustness", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "get_gene_set_store", lambda: store)


@pytest.mark.asyncio
async def test_a_run_over_a_saved_set_records_that_sets_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _SetStore(_gene_set(_SET_GENES))
    _install(monkeypatch, store)

    exp = await run_experiment(_config(gene_set_id=_SET_ID), user_id="u1")

    assert store.asked == [_SET_ID]
    assert exp.gene_set_membership == GeneSetMembership.of(_SET_GENES)
    assert exp.gene_set_membership is not None
    assert exp.gene_set_membership.gene_count == 3


@pytest.mark.asyncio
async def test_a_run_that_names_no_set_records_no_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _SetStore(_gene_set(_SET_GENES))
    _install(monkeypatch, store)

    exp = await run_experiment(_config(gene_set_id=None), user_id="u1")

    assert store.asked == []
    assert exp.gene_set_membership is None


@pytest.mark.asyncio
async def test_a_run_whose_set_has_gone_records_no_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _SetStore(None)
    _install(monkeypatch, store)

    exp = await run_experiment(_config(gene_set_id=_SET_ID), user_id="u1")

    assert store.asked == [_SET_ID]
    assert exp.gene_set_membership is None


@pytest.mark.asyncio
async def test_the_recorded_membership_survives_the_stored_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _SetStore(_gene_set(_SET_GENES))
    _install(monkeypatch, store)

    exp = await run_experiment(_config(gene_set_id=_SET_ID), user_id="u1")
    reread = experiment_from_json(dict(experiment_to_json(exp)))

    assert reread.gene_set_membership == GeneSetMembership.of(_SET_GENES)


def test_an_experiment_stored_before_this_record_reads_as_unrecorded() -> None:
    stored = {
        "id": "exp_be482afb7a03",
        "config": _config(gene_set_id=_SET_ID).model_dump(by_alias=True),
        "status": "completed",
        "createdAt": "2026-09-15T09:00:00Z",
    }

    reread = experiment_from_json(stored)

    assert reread.id == "exp_be482afb7a03"
    assert reread.config.gene_set_id == _SET_ID
    assert reread.gene_set_membership is None
