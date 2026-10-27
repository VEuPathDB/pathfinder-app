from __future__ import annotations

from collections.abc import Collection, Mapping

import pytest

from pathfinder.ai.agents import frame_reading_checks
from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_SEARCH = "GroupsByPhyleticPattern"
_EXPRESSION = "phyletic_expression"
_READINGS = ["MICR>=1T AND MICR<=3T", "MICR>=1T AND MICR<=5T"]


def _asked() -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question="How many Microsporidia genomes at most?",
                recommended_value=_READINGS[0],
                criterion_id="c_families",
                param_name=_EXPRESSION,
                readings=[Reading(label=value, value=value) for value in _READINGS],
            )
        ],
    )


async def _held(
    monkeypatch: pytest.MonkeyPatch,
    listed: dict[str, str],
    *,
    held_class: str | None = None,
    discovered_class: str | None = None,
) -> tuple[FrameResult, list[str]]:
    spelled: list[str] = []

    async def _listed(_site: str, names: Collection[str]) -> dict[str, str]:
        return {name: listed[name] for name in names if name in listed}

    async def _spelling(
        _site: str,
        record_type: str,
        _criterion: Criterion,
        _param: str,
        wire: str,
        _expressions: Mapping[str, str],
    ) -> str:
        spelled.append(record_type)
        return wire

    monkeypatch.setattr(frame_reading_checks, "search_record_types", _listed)
    monkeypatch.setattr(frame_reading_checks, "site_spelling", _spelling)
    ctx = agent_run_context(site_id="orthomcl")
    if discovered_class is not None:
        ctx.deps.agent_state.register_search(
            _SEARCH,
            SearchOverview(
                search_name=_SEARCH,
                display_name="Phyletic pattern",
                record_type=discovered_class,
                description="",
                parameter_names=[_EXPRESSION],
                required_params=[_EXPRESSION],
            ),
        )
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[
            Criterion(
                id="c_families",
                text="families in a handful of microsporidia",
                search_name=_SEARCH,
                record_class=held_class,
                open_params=[OpenSlot(param_name=_EXPRESSION, param_kind="string")],
            )
        ]
    )
    held = await hold_the_readings_to_the_site(ctx, _asked())
    assert isinstance(held, FrameResult)
    return held, spelled


async def test_a_criterion_with_no_class_is_read_under_the_class_the_catalog_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, spelled = await _held(monkeypatch, {_SEARCH: "group"})

    assert (spelled, held.gaps) == (["group", "group"], [])


async def test_the_class_a_criterion_holds_is_read_before_the_discovered_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, spelled = await _held(
        monkeypatch, {}, held_class="group", discovered_class="transcript"
    )

    assert (spelled, held.gaps) == (["group", "group"], [])


async def test_a_criterion_with_no_class_is_not_classed_by_the_discovered_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, spelled = await _held(
        monkeypatch, {_SEARCH: "group"}, discovered_class="transcript"
    )

    assert (spelled, held.gaps) == (["group", "group"], [])


async def test_a_class_the_catalog_does_not_know_is_named_and_not_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, spelled = await _held(monkeypatch, {})

    assert spelled == []
    assert [r.value for r in held.open_questions[0].readings] == _READINGS
    assert held.gaps == [
        PassGap(
            kind="record_type_unknown",
            sentence=(
                f"The record type of {_SEARCH} is not known, so the site did not "
                f"check the readings of c_families.{_EXPRESSION}."
            ),
        )
    ]
