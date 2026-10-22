"""A control test's outcome as the worker reports it, with WDK's names for
what it tested, read as the card, the exhibit and the metrics read it."""

from __future__ import annotations

from pydantic import ConfigDict, Field
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.stream_part_payloads import (
    ControlSetSummary,
    ControlTestResults,
    TestedParameter,
)
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    NamedControlSet,
)

VALUE_CHARS = 120


def _shown(value: str) -> str:
    """A parameter value short enough to read in a table cell."""
    if len(value) <= VALUE_CHARS:
        return value
    return f"{value[:VALUE_CHARS].rstrip()} ..."


class ControlCounts(ControlOutcome):
    """What a control test filed, flat as the worker reports it, with WDK's names.

    ``target_label`` and ``parameter_labels`` are what WDK calls the tested
    step and its parameters, and they are empty when WDK did not answer.
    """

    model_config = ConfigDict(extra="ignore")

    target_label: str = ""
    parameter_labels: dict[str, str] = Field(default_factory=dict)
    tunable_parameters: list[str] = Field(default_factory=list)
    control_set: NamedControlSet | None = None

    def positive_controls(self) -> PositiveControls | None:
        """The positive set, or None when the test was given no positives."""
        match (self.positive_recovered_ids, self.positive_missed_ids):
            case (list() as recovered, list() as missed):
                return PositiveControls(recovered_ids=recovered, missed_ids=missed)
            case _:
                return None

    def negative_controls(self) -> NegativeControls | None:
        """The negative set, or None when the test was given no negatives."""
        match (self.negative_admitted_ids, self.negative_excluded_ids):
            case (list() as admitted, list() as excluded):
                return NegativeControls(admitted_ids=admitted, excluded_ids=excluded)
            case _:
                return None

    def measured(self) -> ControlTestResult:
        """The typed result the metrics engine scores."""
        return ControlTestResult(
            target=ControlTargetData(
                search_name=self.search_name,
                step_id=self.step_id,
                estimated_size=self.estimated_size,
            ),
            positive=self.positive_controls(),
            negative=self.negative_controls(),
        )

    def positive_set(self) -> ControlSetSummary | None:
        """The positive set as the exhibit shows it."""
        positive = self.positive_controls()
        if positive is None:
            return None
        return ControlSetSummary(
            controls_count=positive.controls_count,
            intersection_count=positive.intersection_count,
            recall=positive.recall,
            hit_ids=positive.recovered_ids,
            missed_ids=positive.missed_ids,
        )

    def negative_set(self) -> ControlSetSummary | None:
        """The negative set as the exhibit shows it."""
        negative = self.negative_controls()
        if negative is None:
            return None
        return ControlSetSummary(
            controls_count=negative.controls_count,
            intersection_count=negative.intersection_count,
            false_positive_rate=negative.false_positive_rate,
            hit_ids=negative.admitted_ids,
            missed_ids=negative.excluded_ids,
        )

    def evidence(self, wdk_step_id: int | None) -> ControlTestEvidence | None:
        """The test as the card files it, or None when it was given no control."""
        positive = self.positive_controls()
        negative = self.negative_controls()
        if positive is None and negative is None:
            return None
        return ControlTestEvidence(
            tested_label=self.reader_label(),
            wdk_step_id=wdk_step_id,
            control_set=self.control_set,
            positive=None
            if positive is None
            else ControlSetEvidence(
                returned=positive.recovered_ids, not_returned=positive.missed_ids
            ),
            negative=None
            if negative is None
            else ControlSetEvidence(
                returned=negative.admitted_ids, not_returned=negative.excluded_ids
            ),
        )

    def reader_label(self) -> str:
        """What the tested step is called for a reader, never a url segment."""
        if self.target_label != "":
            return self.target_label
        return "the tested step" if self.step_id is None else f"step {self.step_id}"

    def criteria(self) -> list[TestedParameter]:
        """The tested step's parameters, each under the name WDK shows."""
        return [
            TestedParameter(
                label=self.parameter_labels.get(name, name),
                value=_shown(value.to_wire()),
            )
            for name, value in self.parameters.items()
        ]

    def exhibit(self, tool_call_id: str, task_id: str = "") -> ControlTestResults:
        """The numbered exhibit this control test leaves on the thread."""
        return ControlTestResults(
            task_id=task_id,
            tool_call_id=tool_call_id,
            target_step_id=self.step_id,
            target_label=self.reader_label(),
            target_estimated_size=self.estimated_size,
            target_parameters=self.criteria(),
            positive=self.positive_set(),
            negative=self.negative_set(),
        )


__all__ = ["ControlCounts"]
