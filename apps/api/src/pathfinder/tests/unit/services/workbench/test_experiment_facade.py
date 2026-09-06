from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from pathfinder.services.experiment.types import Experiment, ExperimentConfig
from pathfinder.services.workbench import experiments


def _experiment(experiment_id: str) -> Experiment:
    return Experiment(
        id=experiment_id,
        config=ExperimentConfig(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByMolecularWeight",
            parameters={},
            positive_controls=["PF3D7_0102600"],
            negative_controls=[],
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
            name="kinase sweep",
        ),
        user_id=str(uuid4()),
    )


@dataclass
class _RecordingStore:
    held: dict[str, Experiment] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def aget(self, entity_id: str) -> Experiment | None:
        self.asked.append(entity_id)
        return self.held.get(entity_id)


async def test_getting_an_experiment_returns_the_stored_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore(held={"exp-1": _experiment("exp-1")})
    monkeypatch.setattr(experiments, "get_experiment_store", lambda: store)

    found = await experiments.get_experiment("exp-1")

    assert found is not None
    assert found.config.name == "kinase sweep"
    assert store.asked == ["exp-1"]


async def test_getting_an_experiment_the_store_does_not_hold_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore()
    monkeypatch.setattr(experiments, "get_experiment_store", lambda: store)

    assert await experiments.get_experiment("exp-absent") is None
    assert store.asked == ["exp-absent"]
