from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.services.evidence import control_sets
from pathfinder.services.experiment import control_sourcing
from pathfinder.services.experiment.control_sourcing import (
    ResolvedControls,
    StrategyControls,
)


def _response(name: str, positive_ids: list[str]) -> ControlSetResponse:
    return ControlSetResponse(
        id="cs-1",
        name=name,
        site_id="plasmodb",
        record_type="transcript",
        positive_ids=positive_ids,
        negative_ids=[],
        tags=[],
        version=1,
        is_public=False,
        created_at="2026-09-05T00:00:00+00:00",
    )


@dataclass
class _RecordingService:
    """Stands in for ControlSetService and records what the facade passed."""

    created: list[tuple[NewControlSet, UUID]] = field(default_factory=list)
    listed: list[tuple[str, UUID, list[str] | None]] = field(default_factory=list)
    fetched: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def create(self, spec: NewControlSet, *, user_id: UUID) -> ControlSetResponse:
        self.created.append((spec, user_id))
        return _response(spec.name, spec.positive_ids)

    async def list_for_site(
        self, *, site_id: str, user_id: UUID, tags: list[str] | None
    ) -> list[ControlSetResponse]:
        self.listed.append((site_id, user_id, tags))
        return [_response("saved kinases", ["PF3D7_0102600"])]

    async def get(self, control_set_id: UUID, user_id: UUID) -> ControlSetResponse:
        self.fetched.append((control_set_id, user_id))
        return _response("saved kinases", ["PF3D7_0102600"])


def _install(
    monkeypatch: pytest.MonkeyPatch, service: _RecordingService
) -> AsyncSession:
    monkeypatch.setattr(control_sets, "ControlSetService", lambda _session: service)
    return AsyncSession()


async def test_creating_a_control_set_passes_every_field_to_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _RecordingService()
    session = _install(monkeypatch, service)
    user_id = uuid4()

    created = await control_sets.create_control_set(
        session,
        control_sets.new_control_set(
            name="kinase controls",
            site_id="plasmodb",
            record_type="transcript",
            positive_ids=["PF3D7_0102600"],
            negative_ids=["PF3D7_0107600"],
            source="chat",
        ),
        user_id=user_id,
    )

    assert created.name == "kinase controls"
    spec, spec_user = service.created[0]
    assert spec_user == user_id
    assert spec.site_id == "plasmodb"
    assert spec.record_type == "transcript"
    assert spec.positive_ids == ["PF3D7_0102600"]
    assert spec.negative_ids == ["PF3D7_0107600"]
    assert spec.source == "chat"


async def test_listing_control_sets_asks_for_the_site_without_tag_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _RecordingService()
    session = _install(monkeypatch, service)
    user_id = uuid4()

    found = await control_sets.list_control_sets_for_site(
        session, site_id="plasmodb", user_id=user_id
    )

    assert [cs.name for cs in found] == ["saved kinases"]
    assert service.listed == [("plasmodb", user_id, None)]


async def test_getting_a_control_set_forwards_the_id_and_the_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _RecordingService()
    session = _install(monkeypatch, service)
    control_set_id = uuid4()
    user_id = uuid4()

    found = await control_sets.get_control_set(session, control_set_id, user_id)

    assert found.positive_ids == ["PF3D7_0102600"]
    assert service.fetched == [(control_set_id, user_id)]


async def test_validating_control_ids_reaches_the_sourcing_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, list[str], str]] = []

    async def _validate(
        site_id: str, gene_ids: list[str], *, record_type: str = "transcript"
    ) -> ResolvedControls:
        seen.append((site_id, gene_ids, record_type))
        return ResolvedControls(valid_ids=["PF3D7_0102600"], unresolved_ids=["x"])

    monkeypatch.setattr(control_sourcing, "validate_control_ids", _validate)

    resolved = await control_sets.validate_control_ids(
        "plasmodb", ["PF3D7_0102600", "x"], record_type="gene"
    )

    assert resolved.valid_ids == ["PF3D7_0102600"]
    assert resolved.unresolved_ids == ["x"]
    assert seen == [("plasmodb", ["PF3D7_0102600", "x"], "gene")]


async def test_control_ids_from_a_saved_gene_set_reach_the_sourcing_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[UUID, str]] = []

    async def _from_gene_set(user_id: UUID, gene_set_id: str) -> list[str]:
        seen.append((user_id, gene_set_id))
        return ["PF3D7_0102600", "PF3D7_0107600"]

    monkeypatch.setattr(
        control_sourcing, "control_ids_from_saved_gene_set", _from_gene_set
    )
    user_id = uuid4()

    ids = await control_sets.control_ids_from_saved_gene_set(user_id, "gs-1")

    assert ids == ["PF3D7_0102600", "PF3D7_0107600"]
    assert seen == [(user_id, "gs-1")]


async def test_control_ids_from_a_strategy_reach_the_sourcing_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[UUID, str, UUID]] = []

    async def _from_strategy(
        session: AsyncSession,
        conversation_id: UUID,
        site_id: str,
        user_id: UUID,
    ) -> StrategyControls:
        del session
        seen.append((conversation_id, site_id, user_id))
        return StrategyControls(gene_ids=["PF3D7_0102600"])

    monkeypatch.setattr(control_sourcing, "control_ids_from_strategy", _from_strategy)
    conversation_id = uuid4()
    user_id = uuid4()

    result = await control_sets.control_ids_from_strategy(
        AsyncSession(), conversation_id, "plasmodb", user_id
    )

    assert result.gene_ids == ["PF3D7_0102600"]
    assert seen == [(conversation_id, "plasmodb", user_id)]
