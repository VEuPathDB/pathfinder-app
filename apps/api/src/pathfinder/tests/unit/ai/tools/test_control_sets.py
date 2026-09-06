"""The Lead's control-set tools: validate IDs against WDK, persist a set,
report what did not resolve, list what exists, and refuse a WDK id."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.tools.standalone import control_sets
from pathfinder.ai.tools.standalone.control_sets import (
    build_control_set,
    import_control_ids_from_strategy,
    list_control_sets,
)
from pathfinder.services.experiment.control_sourcing import ResolvedControls
from pathfinder.tests.unit.ai.tools.conftest import runtime_ctx

_WDK_STRATEGY_ID = "330531493"


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
    created = MagicMock()
    created.id = "cs_123"
    created.name = "my controls"
    persisted: list[Any] = []

    async def _create(_session: Any, spec: Any, *, user_id: Any) -> Any:
        del user_id
        persisted.append(spec)
        return created

    monkeypatch.setattr(control_sets, "create_control_set", _create)

    out = (
        await build_control_set(
            runtime_ctx(),
            name="my controls",
            positive_ids=["g1", "typo", "g2"],
            negative_ids=["n1"],
        )
    ).return_value

    assert out.control_set_id == "cs_123"
    assert out.positive_count == 2
    assert out.negative_count == 1
    assert out.unresolved_positive == ["typo"]
    assert [spec.positive_ids for spec in persisted] == [["g1", "g2"]]
    assert persisted[0].negative_ids == ["n1"]
    assert persisted[0].source == "chat"


async def test_build_control_set_refuses_when_no_positive_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validate(
        monkeypatch,
        {"bad1,bad2": ResolvedControls(valid_ids=[], unresolved_ids=["bad1", "bad2"])},
    )

    persisted: list[Any] = []

    async def _create(_session: Any, spec: Any, *, user_id: Any) -> Any:
        del user_id
        persisted.append(spec)
        return MagicMock()

    monkeypatch.setattr(control_sets, "create_control_set", _create)

    with pytest.raises(ModelRetry, match="No positive control"):
        await build_control_set(runtime_ctx(), name="x", positive_ids=["bad1", "bad2"])

    assert persisted == []


async def test_list_control_sets_summarizes(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = MagicMock()
    stored.id = "cs_1"
    stored.name = "set"
    stored.positive_ids = ["g1", "g2"]
    stored.negative_ids = ["n1"]

    async def _list(_session: Any, *, site_id: str, user_id: Any) -> list[Any]:
        del site_id, user_id
        return [stored]

    monkeypatch.setattr(control_sets, "list_control_sets_for_site", _list)

    out = (await list_control_sets(runtime_ctx())).return_value

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
            await import_control_ids_from_strategy(runtime_ctx(), _WDK_STRATEGY_ID)

    async def test_the_message_names_the_value_it_got(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await import_control_ids_from_strategy(runtime_ctx(), _WDK_STRATEGY_ID)

        assert _WDK_STRATEGY_ID in str(err.value)

    async def test_the_message_says_which_id_is_wanted(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await import_control_ids_from_strategy(runtime_ctx(), _WDK_STRATEGY_ID)

        assert "conversation" in str(err.value).lower()
