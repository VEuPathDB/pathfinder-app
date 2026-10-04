"""The counts one control test of a turn returned, as the facts part shows them."""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict

from pathfinder.domain.evidence import ControlTestEvidence


class ControlResultFact(CamelModel):
    """How many of each control set one test of this turn returned."""

    model_config = ConfigDict(frozen=True)

    tested_label: str
    positives_returned: int | None = None
    positives_total: int | None = None
    negatives_returned: int | None = None
    negatives_total: int | None = None

    @computed
    def sentence(self) -> str:
        clauses = [
            f"{returned} of {total} {kind} controls returned"
            for kind, returned, total in (
                ("positive", self.positives_returned, self.positives_total),
                ("negative", self.negatives_returned, self.negatives_total),
            )
            if total is not None
        ]
        return f"{self.tested_label}: {'; '.join(clauses)}"

    def redacted(self, redact: Callable[[str], str]) -> ControlResultFact:
        return self.model_copy(update={"tested_label": redact(self.tested_label)})


def control_result_fact(test: ControlTestEvidence) -> ControlResultFact:
    """The counts one control test measured, without the ids it filed."""
    positive, negative = test.positive, test.negative
    return ControlResultFact(
        tested_label=test.tested_label,
        positives_returned=None if positive is None else positive.returned_count,
        positives_total=None if positive is None else positive.controls_count,
        negatives_returned=None if negative is None else negative.returned_count,
        negatives_total=None if negative is None else negative.controls_count,
    )


__all__ = ["ControlResultFact", "control_result_fact"]
