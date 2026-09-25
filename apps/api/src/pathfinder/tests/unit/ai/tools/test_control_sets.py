"""The Lead's control-set tools: validate IDs against WDK, persist a set,
report what did not resolve, list what exists, and refuse a WDK id."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.tools.standalone import control_sets
from pathfinder.ai.tools.standalone.control_sets import (
    BuiltControlSet,
    ControlSetIds,
    ControlSetSummary,
    build_control_set,
    list_control_sets,
    read_control_set,
    read_gene_ids_from_gene_set,
    read_gene_ids_from_strategy,
)
from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.services.experiment.control_sourcing import ResolvedControls
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import detached_lead_context

_WDK_STRATEGY_ID = "330531493"
_SAVES_NOTHING = "This saves nothing. Call build_control_set to save a control set."


def _stored(
    *,
    control_set_id: str,
    name: str,
    positive_ids: list[str] | None = None,
    negative_ids: list[str] | None = None,
) -> ControlSetResponse:
    """A persisted control set, as the service hands one back."""
    return ControlSetResponse(
        id=control_set_id,
        name=name,
        site_id="plasmodb",
        record_type="transcript",
        positive_ids=positive_ids or [],
        negative_ids=negative_ids or [],
        tags=[],
        version=1,
        is_public=False,
        created_at="2026-01-01T00:00:00Z",
    )


def _patch_validate(
    monkeypatch: pytest.MonkeyPatch, results: dict[str, ResolvedControls]
) -> None:
    async def _validate(
        site_id: str, gene_ids: list[str], **_kw: Any
    ) -> ResolvedControls:
        del site_id
        return results.get(",".join(gene_ids), ResolvedControls())

    monkeypatch.setattr(control_sets, "validate_control_ids", _validate)


async def test_build_control_set_validates_persists_and_reports_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validate(
        monkeypatch,
        {
            "g1,typo,g2": ResolvedControls(
                valid_ids=["g1", "g2"], unresolved_ids=["typo"]
            ),
            "n1": ResolvedControls(valid_ids=["n1"], unresolved_ids=[]),
        },
    )
    created = _stored(control_set_id="cs_123", name="my controls")
    persisted: list[NewControlSet] = []

    async def _create(
        _session: AsyncSession, spec: NewControlSet, *, user_id: UUID
    ) -> ControlSetResponse:
        del user_id
        persisted.append(spec)
        return created

    monkeypatch.setattr(control_sets, "create_control_set", _create)

    out = returned(
        await build_control_set(
            detached_lead_context(),
            name="my controls",
            positive_ids=["g1", "typo", "g2"],
            negative_ids=["n1"],
        ),
        BuiltControlSet,
    )

    assert out.control_set_id == "cs_123"
    assert out.positive_count == 2
    assert out.negative_count == 1
    assert out.unresolved_positive == ["typo"]
    assert [spec.positive_ids for spec in persisted] == [["g1", "g2"]]
    assert persisted[0].negative_ids == ["n1"]
    assert persisted[0].source == "chat"


async def test_build_control_set_records_what_the_turn_wrote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The turn contract reads this record to judge what the reply claims."""
    _patch_validate(monkeypatch, {"g1": ResolvedControls(valid_ids=["g1"])})

    async def _create(
        _session: AsyncSession, spec: NewControlSet, *, user_id: UUID
    ) -> ControlSetResponse:
        del user_id
        return _stored(control_set_id="cs_123", name=spec.name)

    monkeypatch.setattr(control_sets, "create_control_set", _create)
    ctx = detached_lead_context()

    await build_control_set(ctx, name="my controls", positive_ids=["g1"])

    recorded = ctx.deps.state.turn_markers.created_control_sets
    assert [(c.id, c.name) for c in recorded] == [("cs_123", "my controls")]


async def test_a_turn_that_only_read_ids_records_no_control_set() -> None:
    """Reading ids is the source step; only the write is the control set."""
    ctx = detached_lead_context()

    with pytest.raises(ModelRetry):
        await read_gene_ids_from_strategy(ctx, _WDK_STRATEGY_ID)

    assert ctx.deps.state.turn_markers.created_control_sets == []


def test_the_reading_tools_say_they_save_nothing() -> None:
    """The name of each says "control", so the description says who writes."""
    described = [
        _SAVES_NOTHING in (tool.__doc__ or "")
        for tool in (
            read_gene_ids_from_gene_set,
            read_gene_ids_from_strategy,
        )
    ]

    assert described == [True, True]


async def test_build_control_set_refuses_when_no_positive_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validate(
        monkeypatch,
        {"bad1,bad2": ResolvedControls(valid_ids=[], unresolved_ids=["bad1", "bad2"])},
    )

    persisted: list[NewControlSet] = []

    async def _create(
        _session: AsyncSession, spec: NewControlSet, *, user_id: UUID
    ) -> ControlSetResponse:
        del user_id
        persisted.append(spec)
        return _stored(control_set_id="cs_unused", name=spec.name)

    monkeypatch.setattr(control_sets, "create_control_set", _create)

    with pytest.raises(ModelRetry, match="No positive control"):
        await build_control_set(
            detached_lead_context(), name="x", positive_ids=["bad1", "bad2"]
        )

    assert persisted == []


async def test_list_control_sets_summarizes(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored(
        control_set_id="cs_1",
        name="set",
        positive_ids=["g1", "g2"],
        negative_ids=["n1"],
    )

    async def _list(
        _session: AsyncSession, *, site_id: str, user_id: UUID
    ) -> list[ControlSetResponse]:
        del site_id, user_id
        return [stored]

    monkeypatch.setattr(control_sets, "list_control_sets_for_site", _list)

    out = returned(
        await list_control_sets(detached_lead_context()), list[ControlSetSummary]
    )

    assert len(out) == 1
    assert out[0].control_set_id == "cs_1"
    assert out[0].positive_count == 2
    assert out[0].negative_count == 1


class TestAWdkStrategyIdIsARetry:
    """The import tool takes a PathFinder UUID while the conversation is full
    of WDK numeric ids; ``UUID()`` on one raises ValueError, which ends the
    turn with a message the user cannot act on."""

    async def test_it_does_not_raise_value_error(self) -> None:
        with pytest.raises(ModelRetry):
            await read_gene_ids_from_strategy(
                detached_lead_context(),
                _WDK_STRATEGY_ID,
            )

    async def test_the_message_names_the_value_it_got(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await read_gene_ids_from_strategy(
                detached_lead_context(),
                _WDK_STRATEGY_ID,
            )

        assert _WDK_STRATEGY_ID in str(err.value)

    async def test_the_message_says_which_id_is_wanted(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await read_gene_ids_from_strategy(
                detached_lead_context(),
                _WDK_STRATEGY_ID,
            )

        assert "conversation" in str(err.value).lower()


_SAVED_SET = "3f9c2b10-5a4e-4d8e-9b1a-2c7d6e5f4a31"


async def test_read_control_set_returns_both_lists_of_the_saved_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positives = [f"PF3D7_{n:07d}" for n in range(100600, 100680)]
    negatives = [f"PF3D7_{n:07d}" for n in range(111300, 111340)]

    async def _get(
        _session: AsyncSession, control_set_id: UUID, user_id: UUID
    ) -> ControlSetResponse:
        del user_id
        return _stored(
            control_set_id=str(control_set_id),
            name="PF3D7 signal peptide controls",
            positive_ids=positives,
            negative_ids=negatives,
        )

    monkeypatch.setattr(control_sets, "get_control_set", _get)

    out = returned(
        await read_control_set(detached_lead_context(), _SAVED_SET), ControlSetIds
    )

    assert (out.control_set_id, out.name) == (
        _SAVED_SET,
        "PF3D7 signal peptide controls",
    )
    assert (out.positive_ids, out.negative_ids) == (positives, negatives)


async def test_read_control_set_refuses_an_id_that_is_not_a_control_set() -> None:
    with pytest.raises(ModelRetry) as raised:
        await read_control_set(detached_lead_context(), _WDK_STRATEGY_ID)

    assert "control_set_id must be a PathFinder control set id" in str(raised.value)
