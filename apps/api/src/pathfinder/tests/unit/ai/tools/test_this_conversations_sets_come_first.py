"""A listing of saved sets names this conversation's sets first, each marked.

The account holds sets from every conversation, so a set's name or its age
never tells the one this conversation saved from another.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.tools.standalone import control_sets, gene_sets, saved_control_sets
from pathfinder.ai.tools.standalone.control_sets import (
    build_control_set,
    list_control_sets,
    use_control_set,
)
from pathfinder.ai.tools.standalone.gene_set_models import GeneSetListResponse
from pathfinder.ai.tools.standalone.saved_control_sets import ControlSetSummary
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.services.evidence.control_sets import SavedControls
from pathfinder.services.experiment.control_sourcing import ResolvedControls
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.gene_set_store import keep_saved
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    detached_lead_context,
)

_THIS = uuid4()
_OTHER = uuid4()


def _gene_set(
    set_id: str, name: str, count: int, saved_in: UUID | None, day: int
) -> GeneSet:
    return GeneSet(
        id=set_id,
        name=name,
        site_id="plasmodb",
        gene_ids=[f"PF3D7_{n:07d}" for n in range(count)],
        source="strategy",
        conversation_id=saved_in,
        created_at=datetime(2026, 9, day, tzinfo=UTC),
    )


# Newest first, as the store lists them: the set this conversation saved is
# neither the newest nor the one named after the strategy.
_ACCOUNT_GENE_SETS = [
    _gene_set(
        "gs-auto", "Plasmodium Sporozoite Surface Vaccine Antigens", 549, None, 28
    ),
    _gene_set("gs-older", "kinases from last week", 120, _OTHER, 27),
    _gene_set("gs-here", "vaccine candidates draft", 39, _THIS, 26),
]


async def test_the_gene_sets_this_conversation_saved_come_first_and_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return list(_ACCOUNT_GENE_SETS)

    monkeypatch.setattr(gene_sets, "list_stored_gene_sets", _listed)
    ctx = agent_run_context()
    ctx.deps.conversation_id = _THIS

    listed = returned(await gene_sets.list_gene_sets(ctx), GeneSetListResponse)

    assert [(s.name, s.gene_count, s.saved_here) for s in listed.gene_sets] == [
        ("vaccine candidates draft", 39, True),
        ("Plasmodium Sporozoite Surface Vaccine Antigens", 549, False),
        ("kinases from last week", 120, False),
    ]
    assert listed.model_dump(by_alias=True)["geneSets"][0]["savedHere"] is True


async def test_a_saved_gene_set_names_the_conversation_it_was_saved_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept: list[GeneSet] = []
    monkeypatch.setattr(gene_sets, "store_gene_set", keep_saved(kept))
    ctx = agent_run_context()
    ctx.deps.conversation_id = _THIS

    await gene_sets.save_gene_set(
        ctx, name="vaccine candidates draft", gene_ids=["PF3D7_0304600"]
    )

    assert [(gs.name, gs.conversation_id) for gs in kept] == [
        ("vaccine candidates draft", _THIS)
    ]


def _saved(set_id: str, name: str, saved_in: UUID | None) -> SavedControls:
    return SavedControls(
        control_set_id=set_id,
        name=name,
        positive_ids=["PF3D7_0304600", "PF3D7_1133400"],
        negative_ids=["PF3D7_0100100"],
        conversation_id=saved_in,
    )


_ACCOUNT_CONTROL_SETS = [
    _saved("cs-older", "kinase controls", _OTHER),
    _saved("cs-here", "antigen controls", _THIS),
]


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _listed(
        db_session_factory: object, *, site_id: str, user_id: UUID | None
    ) -> list[SavedControls]:
        del db_session_factory, site_id, user_id
        return list(_ACCOUNT_CONTROL_SETS)

    monkeypatch.setattr(control_sets, "saved_control_sets", _listed)
    monkeypatch.setattr(saved_control_sets, "saved_control_sets", _listed)


async def test_the_leads_control_sets_list_this_conversations_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    ctx = detached_lead_context()
    ctx.deps.state.conversation_id = _THIS

    listed = returned(await list_control_sets(ctx), list[ControlSetSummary])

    assert [(s.name, s.saved_here) for s in listed] == [
        ("antigen controls", True),
        ("kinase controls", False),
    ]


async def test_the_checks_control_sets_mark_the_one_saved_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    ctx = agent_run_context(
        control_sets=[
            NamedControlSet(id="cs-older", name="kinase controls"),
            NamedControlSet(id="cs-here", name="antigen controls"),
        ]
    )
    ctx.deps.conversation_id = _THIS

    listed = returned(
        await saved_control_sets.list_control_sets(ctx), list[ControlSetSummary]
    )

    assert [(s.name, s.saved_here) for s in listed] == [
        ("antigen controls", True),
        ("kinase controls", False),
    ]


async def test_an_attached_set_says_whether_it_was_saved_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _one(
        db_session_factory: object,
        control_set_id: str,
        *,
        site_id: str,
        user_id: UUID | None,
    ) -> SavedControls:
        del db_session_factory, site_id, user_id
        return _saved(control_set_id, "kinase controls", _OTHER)

    monkeypatch.setattr(control_sets, "saved_control_set", _one)
    ctx = detached_lead_context()
    ctx.deps.state.conversation_id = _THIS

    attached = returned(await use_control_set(ctx, "cs-older"), ControlSetSummary)

    assert (attached.name, attached.saved_here) == ("kinase controls", False)


async def test_a_built_control_set_names_the_conversation_it_was_saved_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _validate(
        site_id: str, gene_ids: list[str], *, record_type: str
    ) -> ResolvedControls:
        del site_id, record_type
        return ResolvedControls(valid_ids=gene_ids)

    persisted: list[tuple[str, UUID | None]] = []

    async def _create(
        _session: AsyncSession,
        spec: NewControlSet,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
    ) -> ControlSetResponse:
        del user_id
        persisted.append((spec.name, conversation_id))
        return ControlSetResponse(
            id="cs-new",
            name=spec.name,
            site_id=spec.site_id,
            record_type=spec.record_type,
            positive_ids=spec.positive_ids,
            negative_ids=spec.negative_ids,
            tags=[],
            version=1,
            is_public=False,
            created_at="2026-09-28T00:00:00Z",
        )

    monkeypatch.setattr(control_sets, "validate_control_ids", _validate)
    monkeypatch.setattr(control_sets, "create_control_set", _create)
    ctx = detached_lead_context()
    ctx.deps.state.conversation_id = _THIS

    await build_control_set(ctx, name="antigen controls", positive_ids=["g1"])

    assert persisted == [("antigen controls", _THIS)]
