from __future__ import annotations

from collections.abc import Collection

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.reference_grammar import A_REFERENCE, reference_kind
from pathfinder.domain.strategy.computed_groups import ComparisonFacts, HeldComparison
from pathfinder.domain.strategy.operational_spec import OperationalSpec

type Written = frozenset[tuple[str, str]]

_FACT_KINDS = ("stat", "cite")


def written_references(prose: str) -> Written:
    return frozenset(
        (reference_kind(match), match.group("body") or "")
        for match in A_REFERENCE.finditer(prose)
    )


class PlacedComparison(CamelModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str
    facts: ComparisonFacts
    steps: tuple[str, ...]
    root: bool

    def _holds(self, written: Written, paths: Collection[str]) -> bool:
        return any(
            (kind, f"{self.fact_id}.{path}") in written
            for kind in _FACT_KINDS
            for path in paths
        )

    def places_the_count(self, written: Written) -> bool:
        counts = {("count", step) for step in self.steps}
        roots = {("root", "")} if self.root else set()
        return self._holds(written, ("groups",)) or bool(written & (counts | roots))

    def unplaced(self, prose: str) -> list[str]:
        written = written_references(prose)
        if not self.places_the_count(written):
            return []
        return [
            " or ".join(f"[stat:{self.fact_id}.{path}]" for path in need)
            for need in self.facts.breakdown()
            if not self._holds(written, need)
        ]


def placed_comparison(
    held: HeldComparison, spec: OperationalSpec, root_id: str | None
) -> PlacedComparison:
    steps = tuple(held.bound_in(spec))
    return PlacedComparison(
        fact_id=held.fact_id,
        facts=held.facts(),
        steps=steps,
        root=root_id is not None and root_id in steps,
    )


__all__ = ["PlacedComparison", "placed_comparison", "written_references"]
