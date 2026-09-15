"""The route that answers which evaluations a gene set has been through."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.experiment.types import Experiment, ExperimentConfig
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.transport.http.routers.gene_sets import experiments as route_module

USER_ID = uuid4()
SET_ID = "gs-gametocyte-secreted"
UNKNOWN_SET_ID = "gs-nothing-here"


def _experiment(experiment_id: str, created_at: str) -> Experiment:
    return Experiment(
        id=experiment_id,
        config=ExperimentConfig(
            site_id="plasmodb",
            record_type="gene",
            search_name="GenesByTaxon",
            parameters={},
            positive_controls=["PF3D7_0304600"],
            negative_controls=["PF3D7_0930300"],
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
            name="gametocyte secreted (evaluation)",
            gene_set_id=SET_ID,
        ),
        user_id=str(USER_ID),
        status="completed",
        created_at=created_at,
    )


class _SetLookup:
    """Answers for one gene set and refuses every other id."""

    def __init__(self, known_set_id: str) -> None:
        self._known_set_id = known_set_id

    async def get_for_user(self, user_id: UUID, gene_set_id: str) -> GeneSet:
        del user_id
        if gene_set_id != self._known_set_id:
            msg = f"Gene set not found: {gene_set_id}"
            raise NotFoundError(detail=msg)
        return GeneSet(
            id=gene_set_id,
            user_id=USER_ID,
            site_id="plasmodb",
            name="gametocyte secreted",
            gene_ids=["PF3D7_0304600"],
            source="strategy",
            created_at=datetime(2026, 9, 15, tzinfo=UTC),
        )


class _ExperimentLookup:
    """Answers with a fixed list and records what the route asked for."""

    def __init__(self, found: list[Experiment]) -> None:
        self._found = found
        self.asked: tuple[str, UUID] | None = None

    async def alist_for_gene_set(
        self, gene_set_id: str, user_id: UUID
    ) -> list[Experiment]:
        self.asked = (gene_set_id, user_id)
        return self._found


def _install(
    monkeypatch: pytest.MonkeyPatch, found: list[Experiment]
) -> _ExperimentLookup:
    lookup = _ExperimentLookup(found)
    monkeypatch.setattr(route_module, "gene_set_service", lambda: _SetLookup(SET_ID))
    monkeypatch.setattr(route_module, "get_experiment_store", lambda: lookup)
    return lookup


async def test_a_set_with_two_experiments_answers_both_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newer = _experiment("exp-newer", "2026-09-15T09:00:00Z")
    older = _experiment("exp-older", "2026-09-14T09:00:00Z")
    _install(monkeypatch, [newer, older])

    found = await route_module.list_gene_set_experiments(SET_ID, USER_ID)

    assert [exp.id for exp in found] == ["exp-newer", "exp-older"]
    assert found[0].config.gene_set_id == SET_ID


async def test_a_set_with_no_experiment_answers_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [])

    assert await route_module.list_gene_set_experiments(SET_ID, USER_ID) == []


async def test_the_route_asks_only_for_the_calling_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = _install(monkeypatch, [])

    await route_module.list_gene_set_experiments(SET_ID, USER_ID)

    assert lookup.asked == (SET_ID, USER_ID)


async def test_an_unknown_set_is_refused_the_way_its_neighbours_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [])

    with pytest.raises(NotFoundError) as refusal:
        await route_module.list_gene_set_experiments(UNKNOWN_SET_ID, USER_ID)

    assert refusal.value.status == 404
    assert refusal.value.detail == f"Gene set not found: {UNKNOWN_SET_ID}"
