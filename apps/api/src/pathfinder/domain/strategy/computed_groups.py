from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from assistant_core.graph.tool_summary import count_noun
from pydantic import ConfigDict
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.wdk import ComputedComparisonResult, ComputedSet

from pathfinder.domain.statistic_facts import (
    Sentence,
    Share,
    StatisticFact,
    statistic_id,
)
from pathfinder.domain.statistic_rows import model_rows
from pathfinder.domain.strategy.operational_spec import OperationalSpec

COMPARISON_PREFIX = "groups:"
_DIGITS = 12
COMPUTED_ROUTE = "computed snapshot"
LEADS_BY = 2
SNAPSHOT_CAVEAT = (
    "The ids are fixed; a later release maps each id to the groups it became, "
    "so the count can change."
)
SNAPSHOT_NOTE = (
    f"Each step named as a {COMPUTED_ROUTE} holds a saved list of group ids. "
    f"{SNAPSHOT_CAVEAT}"
)

type Route = Literal["computed snapshot"]


def comparison_handle(group_ids: Sequence[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(group_ids)).encode()).hexdigest()
    return f"{COMPARISON_PREFIX}{digest[:_DIGITS]}"


def is_comparison_handle(text: str) -> bool:
    return text.strip().startswith(COMPARISON_PREFIX)


def _share(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else part / whole


class SpeciesFacts(CamelModel):
    model_config = ConfigDict(frozen=True)

    species: str
    genomes: int
    share: Share


class SetFacts(CamelModel):
    model_config = ConfigDict(frozen=True)

    genomes: int
    groups: int
    proteins: int
    leading_species: str
    leading_species_genomes: int
    leading_species_share: Share
    species: tuple[SpeciesFacts, ...]

    @property
    def leading_species_leads(self) -> bool:
        first, *rest = self.species
        return bool(rest) and first.genomes >= LEADS_BY * rest[0].genomes

    @classmethod
    def of(cls, held: ComputedSet) -> SetFacts:
        leading = held.species[0]
        return cls(
            genomes=held.genomes,
            groups=held.groups,
            proteins=held.proteins,
            leading_species=_named(_leaders(held)),
            leading_species_genomes=leading.genomes,
            leading_species_share=_share(leading.genomes, held.genomes),
            species=tuple(
                SpeciesFacts(
                    species=one.species,
                    genomes=one.genomes,
                    share=_share(one.genomes, held.genomes),
                )
                for one in held.species
            ),
        )


class ComparisonFacts(CamelModel):
    model_config = ConfigDict(frozen=True)

    route: Route
    computed_on: str
    reading: Sentence
    groups: int
    both_held: int
    both_held_share: Share
    left_only: int
    left_only_share: Share
    right_only: int
    right_only_share: Share
    ties: int
    residual_groups: int
    residual_groups_share: Share
    probe_requests: int
    compute_requests: int
    left: SetFacts
    right: SetFacts

    def breakdown(self) -> tuple[tuple[str, ...], ...]:
        sides = (("leftOnly", self.left_only), ("rightOnly", self.right_only))
        one_sided = [path for path, count in sides if count]
        split = ["bothHeld", *one_sided] if one_sided else []
        residual = ["residualGroups"] if self.residual_groups else []
        counted = tuple((path, f"{path}Share") for path in (*split, *residual))
        leading = tuple(
            need
            for side, held in (("left", self.left), ("right", self.right))
            if held.leading_species_leads
            for need in (
                (f"{side}.leadingSpecies",),
                (f"{side}.leadingSpeciesShare", f"{side}.leadingSpeciesGenomes"),
            )
        )
        return (*counted, *leading)


def _leaders(held: ComputedSet) -> list[str]:
    most = held.species[0].genomes
    return [one.species for one in held.species if one.genomes == most]


def _named(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _leading(side: str, held: ComputedSet) -> str:
    leading = held.species[0]
    if len(held.species) == 1:
        return (
            f"Every genome of the {side} set is {leading.species} "
            f"({count_noun(held.genomes, 'genome')})."
        )
    shown = f"{round(100 * _share(leading.genomes, held.genomes), 1):g}%"
    leaders = _leaders(held)
    if len(leaders) > 1:
        return (
            f"{_named(leaders)} each hold {leading.genomes:,} of the "
            f"{held.genomes:,} genomes of the {side} set ({shown}), the most of its "
            f"{len(held.species)} species; no one species leads it."
        )
    return (
        f"{leading.species} is {leading.genomes:,} of the {held.genomes:,} genomes "
        f"of the {side} set ({shown}), the most of its {len(held.species)} species."
    )


class HeldComparison(CamelModel):
    model_config = ConfigDict(frozen=True)

    pattern: PhyleticPattern
    answer: ComputedComparisonResult
    computed_on: date
    dataset_id: str | None = None

    @property
    def handle(self) -> str:
        return comparison_handle(self.answer.group_ids)

    @property
    def fact_id(self) -> str:
        return statistic_id("group_comparison", [self.handle])

    def bound_in(self, spec: OperationalSpec) -> list[str]:
        if self.dataset_id is None:
            return []
        saved = InputDatasetValue(dataset_id=self.dataset_id)
        return [c.id for c in spec.criteria if saved in c.param_values.values()]

    def step_name(self, question: str) -> str:
        return f"{question} ({COMPUTED_ROUTE}, {self.computed_on.isoformat()})"

    def description(self, site_name: str) -> str:
        return (
            f"A {COMPUTED_ROUTE} of {site_name}'s data on "
            f"{self.computed_on.isoformat()}: the "
            f"{count_noun(self.answer.groups, 'group')} the comparison selected, "
            f"uploaded as a list. {SNAPSHOT_CAVEAT}"
        )

    def label(self) -> str:
        return f"the {count_noun(self.answer.groups, 'group')} of the comparison"

    def facts(self) -> ComparisonFacts:
        answer = self.answer
        left, right = answer.sets
        return ComparisonFacts(
            route=COMPUTED_ROUTE,
            computed_on=self.computed_on.isoformat(),
            reading=answer.reading,
            groups=answer.groups,
            both_held=answer.both_held,
            both_held_share=_share(answer.both_held, answer.groups),
            left_only=answer.left_only,
            left_only_share=_share(answer.left_only, answer.groups),
            right_only=answer.right_only,
            right_only_share=_share(answer.right_only, answer.groups),
            ties=answer.ties,
            residual_groups=answer.residual_groups,
            residual_groups_share=_share(answer.residual_groups, answer.groups),
            probe_requests=answer.probe_requests,
            compute_requests=answer.compute_requests,
            left=SetFacts.of(left),
            right=SetFacts.of(right),
        )

    def fact(self) -> StatisticFact:
        left, right = self.answer.sets
        return StatisticFact(
            id=self.fact_id,
            kind="group_comparison",
            title=f"Computed comparison: {self.answer.reading}",
            rows=model_rows(self.facts()),
            statements=[
                (
                    f"The groups are a {COMPUTED_ROUTE} of the site's data on "
                    f"{self.computed_on.isoformat()}, not a search the site re-runs."
                ),
                (
                    f"ties counts the {count_noun(self.answer.ties, 'group')} whose "
                    "two sides are equal among every group either set holds, "
                    "selected or not; it is no part of the selected groups."
                ),
                _leading("left", left),
                _leading("right", right),
            ],
        )


def bound_comparisons(
    held: Mapping[str, HeldComparison], spec: OperationalSpec
) -> list[tuple[str, PhyleticPattern]]:
    return [(step, one.pattern) for one in held.values() for step in one.bound_in(spec)]


def noted_description(
    described: str | None, held: Mapping[str, HeldComparison], spec: OperationalSpec
) -> str | None:
    if not bound_comparisons(held, spec):
        return described
    if described is None or not described.strip():
        return SNAPSHOT_NOTE
    if SNAPSHOT_NOTE in described:
        return described
    return f"{described.rstrip()} {SNAPSHOT_NOTE}"


__all__ = [
    "COMPARISON_PREFIX",
    "COMPUTED_ROUTE",
    "LEADS_BY",
    "SNAPSHOT_CAVEAT",
    "SNAPSHOT_NOTE",
    "ComparisonFacts",
    "HeldComparison",
    "SetFacts",
    "SpeciesFacts",
    "comparison_handle",
    "is_comparison_handle",
    "noted_description",
]
