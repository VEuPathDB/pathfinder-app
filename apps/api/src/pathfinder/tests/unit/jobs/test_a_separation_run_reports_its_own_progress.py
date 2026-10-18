"""A separation run's bar moves with the candidates it has measured, and never back."""

from __future__ import annotations

from veupathdb_mcp.separation import SeparationUpdate

from pathfinder.jobs.impls.separate_controls_impl import RunProgress

_COLLECTED = SeparationUpdate(
    phase="collected",
    message="c",
    data={"bySource": {"catalog": 3, "thread": 1}, "skippedByReason": {}},
)


def _measured(candidate_id: str) -> SeparationUpdate:
    return SeparationUpdate(phase="measured", candidate_id=candidate_id, message="m")


def test_each_measured_candidate_advances_the_bar_between_collect_and_assemble() -> (
    None
):
    run = RunProgress()

    written = [
        run.percent(update)
        for update in [
            SeparationUpdate(phase="resolved", message="r"),
            SeparationUpdate(phase="uploaded", message="u"),
            _COLLECTED,
            _measured("c1"),
            _measured("c2"),
            _measured("c3"),
            _measured("c4"),
            SeparationUpdate(phase="assembled", message="a"),
            SeparationUpdate(phase="confirmed", message="f"),
        ]
    ]

    assert [round(p, 3) for p in written] == [
        0.05,
        0.1,
        0.2,
        0.375,
        0.55,
        0.725,
        0.9,
        0.9,
        1.0,
    ]


def test_a_measured_row_past_the_collected_count_stays_below_assembly() -> None:
    run = RunProgress()
    run.percent(_COLLECTED)

    written = [run.percent(_measured(f"c{n}")) for n in range(6)]

    assert round(max(written), 3) == 0.9
    assert written == sorted(written)
