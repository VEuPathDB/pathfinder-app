"""Driving a case: every turn in order on one thread, and the step ids around it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import pytest

from pathfinder.devtools import eval_runner
from pathfinder.devtools.chat import RunArgs
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.scoring import ObservedOutcome


def _case(*turns: str) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=list(turns),
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-08-30",
        ),
    )


class _Capture:
    def __init__(self, text: str) -> None:
        self._text = text

    def assistant_text(self) -> str:
        return self._text


class _Installed(NamedTuple):
    """What the stubs recorded, and the stubs themselves for a test to wrap."""

    driven: list[RunArgs]
    read: list[UUID]
    drive: Callable[[RunArgs], Awaitable[tuple[_Capture, object]]]
    step_ids: Callable[[UUID], Awaitable[set[int]]]


def _install(
    monkeypatch: pytest.MonkeyPatch,
    step_ids: list[set[int]],
) -> _Installed:
    driven: list[RunArgs] = []
    read: list[UUID] = []
    remaining = list(step_ids)

    async def _drive(args: RunArgs) -> tuple[_Capture, object]:
        driven.append(args)
        return _Capture(f"reply to {args.prompt}"), object()

    async def _step_ids(conversation_id: UUID) -> set[int]:
        read.append(conversation_id)
        return remaining.pop(0)

    async def _observe(
        conversation_id: UUID,
        reply_text: str,
        *,
        step_ids_unchanged: bool | None,
    ) -> ObservedOutcome:
        del conversation_id
        return ObservedOutcome(
            built_strategy=True,
            reply_text=reply_text,
            step_ids_unchanged=step_ids_unchanged,
        )

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    return _Installed(driven=driven, read=read, drive=_drive, step_ids=_step_ids)


async def test_the_turns_are_driven_in_order_on_one_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100, 200}, {100, 200}])

    await eval_runner.run_one_case(
        _case("build it", "now change one thing"),
        run_root=tmp_path,
    )

    driven = installed.driven
    assert [args.prompt for args in driven] == ["build it", "now change one thing"]
    assert len({args.conversation_id for args in driven}) == 1
    assert [args.run_dir.name for args in driven] == ["turn-1", "turn-2"]


async def test_step_ids_that_survive_the_last_turn_are_reported_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [{100, 200}, {100, 200}])

    observed = await eval_runner.run_one_case(
        _case("build it", "swap the organism and keep the rest"),
        run_root=tmp_path,
    )

    assert observed.step_ids_unchanged is True
    assert observed.reply_text == "reply to swap the organism and keep the rest"


async def test_a_rebuild_that_mints_new_step_ids_is_reported_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [{100, 200}, {300, 400}])

    observed = await eval_runner.run_one_case(
        _case("build it", "swap the organism and keep the rest"),
        run_root=tmp_path,
    )

    assert observed.step_ids_unchanged is False


async def test_a_thread_that_held_no_step_before_the_last_turn_observes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set(), {100, 200}])

    observed = await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    assert observed.step_ids_unchanged is None


async def test_the_read_happens_before_the_last_turn_and_after_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []
    installed = _install(monkeypatch, [{100}, {100}])

    async def _drive(args: RunArgs) -> tuple[_Capture, object]:
        order.append(f"turn:{args.prompt}")
        return await installed.drive(args)

    async def _step_ids(conversation_id: UUID) -> set[int]:
        order.append("read")
        return await installed.step_ids(conversation_id)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)

    await eval_runner.run_one_case(_case("one", "two"), run_root=tmp_path)

    assert order == ["turn:one", "read", "turn:two", "read"]
