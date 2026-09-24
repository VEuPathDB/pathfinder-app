from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from pathfinder.services.evidence import gene_sets
from pathfinder.services.gene_sets.types import GeneSet


def _gene_set(name: str, user_id: UUID | None) -> GeneSet:
    return GeneSet(
        id=f"gs-{name}",
        name=name,
        site_id="plasmodb",
        gene_ids=["PF3D7_0102600", "PF3D7_0107600"],
        source="paste",
        user_id=user_id,
        created_at=datetime.now(UTC),
    )


@dataclass
class _RecordingStore:
    """Answers the two list calls and records which one the facade chose."""

    all_sets: list[GeneSet] = field(default_factory=list)
    user_sets: list[GeneSet] = field(default_factory=list)
    calls: list[tuple[str, UUID | None, str | None]] = field(default_factory=list)
    saved: list[GeneSet] = field(default_factory=list)

    async def alist_all(self, *, site_id: str | None = None) -> list[GeneSet]:
        self.calls.append(("alist_all", None, site_id))
        return self.all_sets

    async def alist_for_user(
        self, user_id: UUID, *, site_id: str | None = None
    ) -> list[GeneSet]:
        self.calls.append(("alist_for_user", user_id, site_id))
        return self.user_sets

    async def aget(self, entity_id: str) -> GeneSet | None:
        self.calls.append(("aget", None, entity_id))
        return next((gs for gs in self.all_sets if gs.id == entity_id), None)

    def save(self, entity: GeneSet) -> None:
        self.saved.append(entity)


def _install(monkeypatch: pytest.MonkeyPatch, store: _RecordingStore) -> None:
    monkeypatch.setattr(gene_sets, "get_gene_set_store", lambda: store)


async def test_listing_for_a_user_asks_the_store_for_that_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    store = _RecordingStore(user_sets=[_gene_set("mine", user_id)])
    _install(monkeypatch, store)

    found = await gene_sets.list_stored_gene_sets(site_id="plasmodb", user_id=user_id)

    assert [gs.name for gs in found] == ["mine"]
    assert store.calls == [("alist_for_user", user_id, "plasmodb")]


async def test_listing_without_a_user_asks_the_store_for_the_whole_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore(all_sets=[_gene_set("everyones", None)])
    _install(monkeypatch, store)

    found = await gene_sets.list_stored_gene_sets(site_id="toxodb", user_id=None)

    assert [gs.name for gs in found] == ["everyones"]
    assert store.calls == [("alist_all", None, "toxodb")]


async def test_getting_a_gene_set_returns_the_stored_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore(all_sets=[_gene_set("kinases", None)])
    _install(monkeypatch, store)

    found = await gene_sets.get_gene_set("gs-kinases")

    assert found is not None
    assert found.gene_ids == ["PF3D7_0102600", "PF3D7_0107600"]


async def test_getting_an_unknown_gene_set_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore()
    _install(monkeypatch, store)

    assert await gene_sets.get_gene_set("gs-absent") is None
    assert store.calls == [("aget", None, "gs-absent")]


def test_saving_a_gene_set_writes_it_to_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _RecordingStore()
    _install(monkeypatch, store)
    gs = _gene_set("gametocyte markers", None)

    gene_sets.store_gene_set(gs)

    assert [saved.id for saved in store.saved] == ["gs-gametocyte markers"]
