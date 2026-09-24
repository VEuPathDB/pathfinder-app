"""What one turn did to the spec it started from.

A criterion is kept, changed, added or dropped. The comparison is computed from
the two specs, so no prose can claim a criterion was preserved that was not.
"""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import computed
from pydantic import Field
from veupathdb.domain.parameters import to_wire
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

__all__ = ["CriterionChange", "CriterionDisposition", "SpecDiff", "diff_specs"]

CriterionDisposition = Literal["kept", "changed", "added", "dropped"]


class CriterionChange(CamelModel):
    """One criterion's fate across a turn.

    ``changed_params`` names every parameter whose value the turn moved, in
    wire form, ``removed_params`` every one it took away, and
    ``rebound_search`` says whether it put the criterion on another search.
    Together they are the whole account of a change; the values to push come
    from the spec itself.
    """

    criterion_id: str
    disposition: CriterionDisposition
    changed_params: dict[str, str] = Field(default_factory=dict)
    removed_params: list[str] = Field(default_factory=list)
    rebound_search: bool = False
    reason: str = ""


class SpecDiff(CamelModel):
    changes: list[CriterionChange] = Field(default_factory=list)
    structure_changed: bool = False

    @computed
    def kept_count(self) -> int:
        return self._count("kept")

    @computed
    def changed_count(self) -> int:
        return self._count("changed")

    @computed
    def added_count(self) -> int:
        return self._count("added")

    @computed
    def dropped_count(self) -> int:
        return self._count("dropped")

    def _count(self, disposition: CriterionDisposition) -> int:
        return sum(1 for c in self.changes if c.disposition == disposition)

    def touched_count(self) -> int:
        """Criteria this turn added, changed or dropped, and the shape it rewired.

        A rewire moves the result set without touching a criterion, so it counts
        as one touch.
        """
        touched = sum(1 for c in self.changes if c.disposition != "kept")
        return touched + (1 if self.structure_changed else 0)

    def render(self) -> str:
        counts = (
            f"kept {self.kept_count}, changed {self.changed_count}, "
            f"added {self.added_count}, dropped {self.dropped_count}"
        )
        return f"{counts}, structure rewired" if self.structure_changed else counts


def diff_specs(before: OperationalSpec, after: OperationalSpec) -> SpecDiff:
    """Compare two specs by criterion id and by bound parameter value."""
    after_by_id = {c.id: c for c in after.criteria}
    changes = [
        _change_for(criterion, after_by_id.get(criterion.id))
        for criterion in before.criteria
    ]
    before_ids = {c.id for c in before.criteria}
    changes.extend(
        CriterionChange(
            criterion_id=criterion.id,
            disposition="added",
            changed_params=_wire(criterion),
        )
        for criterion in after.criteria
        if criterion.id not in before_ids
    )
    return SpecDiff(
        changes=changes,
        structure_changed=before.structure != after.structure,
    )


def _change_for(before: Criterion, after: Criterion | None) -> CriterionChange:
    if after is None:
        return CriterionChange(
            criterion_id=before.id,
            disposition="dropped",
            reason=before.text,
        )
    if before.analysis is not None or after.analysis is not None:
        return _analysis_change(before, after)
    before_params = _wire(before)
    after_params = _wire(after)
    rebound = before.search_name != after.search_name
    removed = sorted(set(before_params) - set(after_params))
    changed = {
        name: value
        for name, value in after_params.items()
        if before_params.get(name) != value
    }
    if not changed and not removed and not rebound:
        return CriterionChange(criterion_id=before.id, disposition="kept")
    return CriterionChange(
        criterion_id=before.id,
        disposition="changed",
        changed_params=changed,
        removed_params=removed,
        rebound_search=rebound,
    )


def _analysis_change(before: Criterion, after: Criterion) -> CriterionChange:
    """An analysis is compared by what it selects, never by its document.

    Each compute replaces the one computation an analysis holds, so two
    exports share an analysis id, and the document a step carries names none.
    A binding that selects other genes is restated whole.
    """
    if before.search_name == after.search_name and _meaning(before) == _meaning(after):
        return CriterionChange(criterion_id=before.id, disposition="kept")
    return CriterionChange(
        criterion_id=before.id, disposition="changed", rebound_search=True
    )


def _meaning(criterion: Criterion) -> AnalysisBinding | None:
    return None if criterion.analysis is None else criterion.analysis.meaning()


def _wire(criterion: Criterion) -> dict[str, str]:
    return {name: to_wire(value) for name, value in criterion.resolved_params.items()}
