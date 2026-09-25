"""The control results one message already holds, merged per tested target."""

from collections.abc import Iterable

from assistant_core.platform.pydantic_base import CamelModel
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence


def _merged_set(sets: Iterable[ControlSetEvidence | None]) -> ControlSetEvidence | None:
    """Every id of the sets once, filed as the latest set that tested it."""
    filed: dict[str, bool] = {}
    for held in sets:
        if held is None:
            continue
        filed.update(dict.fromkeys(held.returned, True))
        filed.update(dict.fromkeys(held.not_returned, False))
    if not filed:
        return None
    return ControlSetEvidence(
        returned=[gene_id for gene_id, returned in filed.items() if returned],
        not_returned=[gene_id for gene_id, returned in filed.items() if not returned],
    )


def merged_control_tests(
    tests: Iterable[ControlTestEvidence],
) -> list[ControlTestEvidence]:
    """One test per tested target, holding every control id it was tested with."""
    by_target: dict[tuple[int | None, str], list[ControlTestEvidence]] = {}
    for tested in tests:
        by_target.setdefault((tested.wdk_step_id, tested.tested_label), []).append(
            tested
        )
    return [
        ControlTestEvidence(
            tested_label=label,
            wdk_step_id=step,
            positive=_merged_set(tested.positive for tested in held),
            negative=_merged_set(tested.negative for tested in held),
        )
        for (step, label), held in by_target.items()
    ]


def _filed(
    held: ControlSetEvidence | None, asked: list[str]
) -> tuple[list[str], list[str]] | None:
    """The asked ids split as ``held`` filed them; None when one was never tested."""
    returned = set() if held is None else set(held.returned)
    not_returned = set() if held is None else set(held.not_returned)
    if not set(asked) <= returned | not_returned:
        return None
    return (
        [gene_id for gene_id in asked if gene_id in returned],
        [gene_id for gene_id in asked if gene_id in not_returned],
    )


class RepeatedControlTest(CamelModel):
    """A test of ids this message already tested on the step, with no new task."""

    note: str
    outcome: ControlOutcome


def repeated_control_test(
    markers: TurnMarkers,
    wdk_step_id: int,
    positive_controls: list[str] | None,
    negative_controls: list[str] | None,
) -> ControlOutcome | None:
    """The asked ids as this message's tests of the step filed them.

    None when an asked id was not tested on the step under this message.
    """
    if not positive_controls and not negative_controls:
        return None
    for tested in merged_control_tests(
        run.evidence
        for run in markers.control_tests
        if run.origin == "control_test" and run.evidence.wdk_step_id == wdk_step_id
    ):
        positive = _filed(tested.positive, positive_controls or [])
        negative = _filed(tested.negative, negative_controls or [])
        if positive is None or negative is None:
            continue
        return ControlOutcome(
            step_id=wdk_step_id,
            positive_recovered_ids=positive[0] if positive_controls else None,
            positive_missed_ids=positive[1] if positive_controls else None,
            negative_admitted_ids=negative[0] if negative_controls else None,
            negative_excluded_ids=negative[1] if negative_controls else None,
        )
    return None


__all__ = ["RepeatedControlTest", "merged_control_tests", "repeated_control_test"]
