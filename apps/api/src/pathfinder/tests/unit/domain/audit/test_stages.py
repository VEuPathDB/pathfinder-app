"""The four stages of a run, which one a resumed run starts from, and its request count."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.audit.stages import STAGES, RunStages


def _finished() -> RunStages:
    stages = RunStages()
    for name in STAGES:
        stages = stages.finish(name)
    return stages


def test_a_new_run_starts_at_collect() -> None:
    stages = RunStages()
    assert stages.next_stage == "collect"
    assert stages.unfinished == STAGES


def test_a_stage_finishes_only_in_order() -> None:
    stages = RunStages().finish("collect")
    assert stages.next_stage == "screen"
    with pytest.raises(ValueError, match="confirm is not the next stage; screen is"):
        stages.finish("confirm")


def test_a_finished_run_has_no_next_stage() -> None:
    assert (_finished().next_stage, _finished().unfinished) == (None, ())


def test_reopening_a_stage_reopens_every_later_one_and_keeps_the_requests() -> None:
    stages = _finished().count("collect", 4).count("confirm", 6).reopen("confirm")
    assert stages.unfinished == ("confirm", "tie_break")
    assert stages.requests == 10


def test_requests_add_up_across_resumes() -> None:
    stages = RunStages().count("collect", 3).count("collect", 2).count("screen", 1)
    assert stages.requests == 6
    assert [s.requests for s in stages.stages] == [5, 1, 0, 0]


def test_store_reads_add_up_apart_from_the_requests() -> None:
    stages = (
        RunStages().count("confirm", 3, 45).count("confirm", 2, 5).count("screen", 1)
    )
    assert (stages.requests, stages.store_reads) == (6, 50)
    assert [s.store_reads for s in stages.stages] == [0, 0, 50, 0]


def test_a_stored_list_that_finishes_out_of_order_is_refused() -> None:
    stored = {
        "stages": [
            {"name": "collect", "finished": False, "requests": 0},
            {"name": "screen", "finished": True, "requests": 0},
            {"name": "confirm", "finished": False, "requests": 0},
            {"name": "tie_break", "finished": False, "requests": 0},
        ]
    }
    with pytest.raises(
        ValidationError, match="a stage finishes only after the stages before it"
    ):
        RunStages.model_validate(stored)


def test_a_stored_list_round_trips_its_wire_form() -> None:
    stages = RunStages().count("collect", 4).finish("collect")
    assert (
        RunStages.model_validate(stages.model_dump(by_alias=True, mode="json"))
        == stages
    )


def test_a_halt_reason_rides_every_change_until_it_is_cleared() -> None:
    halted = RunStages().halt("sign-in needed")
    changed = halted.count("collect", 2).finish("collect").reopen("collect")
    assert changed.halted == "sign-in needed"
    assert changed.halt(None).halted is None
    assert RunStages().halted is None


def test_a_stage_keeps_its_progress_through_counts_and_finishing() -> None:
    stages = (
        RunStages()
        .progress("collect", done=3, total=9, message="NF54: 5609 genes")
        .count("collect", 2)
        .halt("sign-in needed")
    )
    (collect, *_) = stages.finish("collect").stages
    assert (collect.done, collect.total, collect.message, collect.requests) == (
        3,
        9,
        "NF54: 5609 genes",
        2,
    )
    assert (collect.finished, stages.halted) == (True, "sign-in needed")
    with pytest.raises(ValidationError):
        RunStages.model_validate({"stages": [{"name": n, "done": -1} for n in STAGES]})


def test_the_last_target_failure_rides_every_change_of_the_stages() -> None:
    noted = RunStages().note_target_failure("connection refused")
    changed = (
        noted.count("collect", 1)
        .progress("collect", done=1, total=1, message="m")
        .finish("collect")
        .reopen("collect")
        .halt("sign-in needed")
    )
    assert (changed.target_failure, RunStages().target_failure) == (
        "connection refused",
        None,
    )
