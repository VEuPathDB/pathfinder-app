"""The folds: a criterion the structure leaves out states its values on the
criterion that runs the same search, and an INTERSECT input that states only
the organism its sibling runs on, or matches every gene of it, leaves the
structure."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from pydantic import ConfigDict
from veupathdb.domain.parameters import to_wire
from veupathdb.domain.strategy import CombineOp, extract_output_organisms
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    message_states,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.domain.strategy.organism_scope import (
    organism_params_of,
    universe_key,
)
from pathfinder.domain.strategy.orthology import projected_steps
from pathfinder.domain.strategy.words import stated_run_of, words_of


class FoldedSpec(CamelModel):
    """The spec the fold produced, and the options it could not place."""

    model_config = ConfigDict(frozen=True)

    spec: OperationalSpec
    unplaced: tuple[str, ...] = ()


def stated_wire_values(spec: OperationalSpec | None) -> dict[str, dict[str, str]]:
    """The wire values each criterion of a spec states, by criterion id."""
    if spec is None:
        return {}
    return {
        criterion.id: {
            name: to_wire(value) for name, value in criterion.param_values.items()
        }
        for criterion in spec.criteria
    }


def fold_option_criteria(
    spec: OperationalSpec,
    *,
    live_step_ids: Collection[str] = (),
    answered_values: Mapping[str, Mapping[str, str]] | None = None,
) -> FoldedSpec:
    """Move an option onto the step that runs its search.

    A criterion the structure leaves out states its values on the criterion that
    names the same search; one no single criterion carries is reported unplaced.
    A criterion the strategy holds a step for runs that step, so it is never an
    option however the structure reads. ``answered_values`` are the values the
    strategy already answers to, which is how a value the carrier only
    inherited is told from one this pass stated for it.
    """
    answered = answered_values or {}
    named = structure_criteria(spec.structure)
    answers_to_a_step = named | frozenset(live_step_ids)
    if all(c.id in answers_to_a_step for c in spec.criteria):
        return FoldedSpec(spec=spec)
    folded = spec.model_copy(deep=True)
    # An analysis states its own document, so it carries no option and is none.
    carriers = [c for c in folded.criteria if c.id in named and c.analysis is None]
    absorbed: set[str] = set()
    unplaced: list[str] = []
    for option in folded.criteria:
        if (
            option.id in answers_to_a_step
            or not option.search_name
            or option.open_params
            or option.analysis is not None
        ):
            continue
        runs_it = [c for c in carriers if c.search_name == option.search_name]
        if len(runs_it) != 1 or not _carry_the_option(
            runs_it[0], option, answered.get(runs_it[0].id, {})
        ):
            unplaced.append(option.id)
            continue
        absorbed.add(option.id)
    if not absorbed:
        return FoldedSpec(spec=spec, unplaced=tuple(unplaced))
    folded.criteria = [c for c in folded.criteria if c.id not in absorbed]
    return FoldedSpec(spec=folded, unplaced=tuple(unplaced))


def carried_values(carrier: Criterion) -> dict[str, str]:
    """The wire values a fold has already carried onto this criterion."""
    return {
        name: to_wire(bound.value)
        for name, bound in carrier.resolved_params.items()
        if bound.carried_from
    }


def _carry_the_option(
    carrier: Criterion, option: Criterion, answered: Mapping[str, str]
) -> bool:
    """Carry the option's values onto the carrier; False when one contradicts a
    value the fold carried. A defaulted value, a wire value the carrier holds, and
    a carrier value set by a statement and not by the answered strategy stay."""
    carried = carried_values(carrier)
    stated: dict[str, BoundValue] = {}
    for name, bound in option.resolved_params.items():
        if bound.source == "default":
            continue
        if name in carried:
            if carried[name] != to_wire(bound.value):
                return False
            continue
        held = carrier.resolved_params.get(name)
        if held is not None and to_wire(held.value) == to_wire(bound.value):
            continue
        if (
            held is not None
            and held.source not in ("default", "chosen")
            and answered.get(name) != to_wire(held.value)
        ):
            continue
        stated[name] = bound.carried(option.id)
    carrier.resolved_params.update(stated)
    if stated:
        carrier.result_count = None
        carrier.measurements = [
            m for m in carrier.measurements if m.param not in stated
        ]
    return True


# The carrier's step meets an organism and a record type, and a combination
# states how criteria join, never a value one leaf binds.
_HELD_BY_THE_CARRIER = frozenset(
    {ConstraintKind.ORGANISM, ConstraintKind.RECORD_TYPE, ConstraintKind.COMBINATION}
)


def restated_requirement(
    text: str, requirements: Sequence[Constraint], request_texts: Sequence[str]
) -> Constraint | None:
    """The researcher's requirement a criterion's text restates.

    A stated requirement whose words the text carries comes first, else the
    longest run of a researcher message the text restates. None when the text
    restates no words of the researcher.
    """
    stated = next(
        (
            c
            for c in requirements
            if c.source is ConstraintSource.USER_EXPLICIT
            and c.kind not in _HELD_BY_THE_CARRIER
            and message_states(text, c.requested_value)
        ),
        None,
    )
    if stated is not None:
        return stated
    run = max((stated_run_of(m, text) for m in request_texts), key=len, default="")
    if not run:
        return None
    return Constraint(
        kind=ConstraintKind.OTHER,
        requested_value=run,
        label=run,
        source=ConstraintSource.USER_EXPLICIT,
    )


class OrganismDrop(CamelModel):
    """An INTERSECT input the organism fold removed, and what became of its text.

    ``met`` is true when the text names only the organism, which the carrier's
    organism value meets; otherwise the binding matched all ``records`` genes
    of the organism and ``requirement`` is the researcher's requirement the
    text restated, which stays open.
    """

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    text: str
    organisms: tuple[str, ...]
    met: bool
    carrier_id: str
    records: int | None = None
    requirement: Constraint | None = None

    @property
    def fate(self) -> str:
        """The drop and the requirement's fate, in one sentence each."""
        named = ", ".join(self.organisms)
        head = f"{self.criterion_id} ('{self.text}') is dropped:"
        if self.met:
            return (
                f"{head} it names only the organism {named}, which "
                f"{self.carrier_id} already runs on, so that organism value meets it."
            )
        dropped = (
            f"{head} it matches all {self.records:,} genes of {named}, which "
            f"{self.carrier_id} already runs on, so it narrows nothing."
        )
        if self.requirement is None:
            return dropped
        return (
            f"{dropped} '{self.requirement.requested_value}' stays open: bind a "
            f"search whose values state it, or end with it as a gap."
        )


class FoldedStructure(CamelModel):
    """The structure the organism fold left, and the inputs it dropped."""

    model_config = ConfigDict(frozen=True)

    structure: SpecStructure
    dropped: tuple[OrganismDrop, ...] = ()

    def holding_open(
        self, requirements: Sequence[Constraint], request_texts: Sequence[str]
    ) -> FoldedStructure:
        """The fold with each unmet drop holding open the requirement its text
        restates."""
        dropped = tuple(
            drop
            if drop.met
            else drop.model_copy(
                update={
                    "requirement": restated_requirement(
                        drop.text, requirements, request_texts
                    )
                }
            )
            for drop in self.dropped
        )
        return self.model_copy(update={"dropped": dropped})


class _Redundant(CamelModel):
    """The organisms a redundant leaf holds; ``records`` is its count when the
    count identity, not its text, makes it redundant."""

    model_config = ConfigDict(frozen=True)

    organisms: frozenset[str]
    records: int | None


class _OrganismReading:
    """What the organism fold reads each INTERSECT input against."""

    def __init__(
        self,
        spec: OperationalSpec,
        organisms: Collection[str],
        record_words: Collection[str],
        universe_counts: Mapping[str, int],
        live_step_ids: Collection[str],
    ) -> None:
        self.by_id = {c.id: c for c in spec.criteria}
        self.marked = organism_params_of(spec.criteria)
        self.organisms = list(organisms)
        self.record_words = {word.casefold() for word in record_words}
        self.universe_counts = universe_counts
        self.live = frozenset(live_step_ids)
        self.dropped: list[OrganismDrop] = []

    def output_of(self, node: StructureNode) -> frozenset[str]:
        steps = projected_steps(node, self.by_id)
        return frozenset(extract_output_organisms(steps, self.marked) or ())

    def carrier_of(self, node: StructureNode) -> str:
        """The criterion whose organism the subtree's output carries.

        A combine's output is its primary input's; a transform's is its own.
        """
        step = projected_steps(node, self.by_id)
        while step.primary_input is not None and step.secondary_input is not None:
            step = step.primary_input
        return step.id

    def redundancy(self, node: StructureNode) -> _Redundant | None:
        """The organisms a droppable leaf holds, and why it is redundant."""
        if node.kind != "leaf":
            return None
        criterion = self.by_id.get(node.named_criterion)
        if criterion is None or criterion.id in self.live:
            return None
        named = self._named_organism(criterion.text)
        if named is not None:
            return _Redundant(organisms=frozenset({named}), records=None)
        key = universe_key(criterion, self.organisms)
        if (
            key is None
            or self.universe_counts.get(criterion.id) != criterion.result_count
        ):
            return None
        return _Redundant(organisms=frozenset(key), records=criterion.result_count)

    def _named_organism(self, text: str) -> str | None:
        """The one organism entry the text names, when its other words are all
        words of the record type's display names."""
        stated = stated_organisms(text, self.organisms)
        if len(stated) != 1:
            return None
        words = words_of(text)
        rest = words[: stated[0].start] + words[stated[0].end :]
        return stated[0].entry if set(rest) <= self.record_words else None


def intersected_leaves(node: StructureNode) -> frozenset[str]:
    """The criteria the tree states as leaf inputs of an INTERSECT."""
    own = frozenset[str]()
    if node.kind == "combine" and node.operator is CombineOp.INTERSECT:
        own = frozenset(
            child.criterion_id
            for child in node.inputs
            if child.kind == "leaf" and child.criterion_id
        )
    return own.union(*(intersected_leaves(child) for child in node.inputs))


def fold_organism_universe(
    spec: OperationalSpec,
    tree: SpecStructure,
    organisms: Collection[str],
    record_words: Collection[str],
    universe_counts: Mapping[str, int],
    *,
    live_step_ids: Collection[str],
) -> FoldedStructure:
    """Drop each INTERSECT input that states only the organism a sibling runs on.

    Such an input is a leaf whose text names one organism entry and words of the
    record type alone, or whose ``organism_only`` binding counts exactly the
    genes ``universe_counts`` holds for it (keyed by criterion id, one count
    per leaf on its own record type). A leaf of unknown count stays. The tree's only leaf, a
    MINUS input, a transform input and a live step are never dropped.
    """
    reading = _OrganismReading(
        spec,
        organisms,
        record_words,
        universe_counts,
        live_step_ids,
    )
    root = _organism_folded(tree.root, reading)
    if not reading.dropped:
        return FoldedStructure(structure=tree)
    return FoldedStructure(
        structure=SpecStructure(root=root), dropped=tuple(reading.dropped)
    )


def _organism_folded(node: StructureNode, reading: _OrganismReading) -> StructureNode:
    inputs = [_organism_folded(child, reading) for child in node.inputs]
    if node.kind != "combine" or node.operator is not CombineOp.INTERSECT:
        return node.model_copy(update={"inputs": inputs})
    kept = list(inputs)
    for candidate in inputs:
        found = reading.redundancy(candidate)
        if found is None:
            continue
        carrier = next(
            (
                s
                for s in kept
                if s is not candidate and reading.output_of(s) == found.organisms
            ),
            None,
        )
        if carrier is None:
            continue
        kept = [s for s in kept if s is not candidate]
        reading.dropped.append(
            OrganismDrop(
                criterion_id=candidate.named_criterion,
                text=reading.by_id[candidate.named_criterion].text,
                organisms=tuple(sorted(found.organisms)),
                met=found.records is None,
                carrier_id=reading.carrier_of(carrier),
                records=found.records,
            )
        )
    if len(kept) == 1:
        return kept[0]
    return node.model_copy(update={"inputs": kept})
