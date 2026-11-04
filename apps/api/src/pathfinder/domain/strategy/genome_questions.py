from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.count_words import counted
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.genome_group import (
    INCLUDED_SPECIES,
    MIN_GROUP_GENOMES,
    GenomeGroup,
    GenomeReading,
)
from pathfinder.domain.strategy.genome_group_steps import required_genomes
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
    structure_criteria,
)
from pathfinder.domain.strategy.question_options import (
    ReadGenomes,
    TypedOption,
    option_id,
)
from pathfinder.domain.strategy.questions import SlotQuestion

_SEARCH = "GenesByOrthologPattern"
_READ_KINDS = frozenset({"any_strain", "all_strains", "not_measurable", "bound_count"})


def _read(criterion: Criterion) -> list[Measurement]:
    return [
        m
        for m in criterion.measurements
        if m.param == INCLUDED_SPECIES and m.kind in _READ_KINDS
    ]


def _at_least_one_count(read: Sequence[Measurement]) -> int | None:
    return next((m.count for m in read if m.kind == "any_strain"), None)


def _asks(criterion: Criterion, named: frozenset[str]) -> bool:
    read = _read(criterion)
    return (
        criterion.id in named
        and criterion.search_name == _SEARCH
        and criterion.genome_group is None
        and not criterion.absence_of
        and not criterion.open_params
        and len(required_genomes(criterion)) >= MIN_GROUP_GENOMES
        and bool(read)
        and _at_least_one_count(read) != criterion.result_count
    )


def _option(
    criterion: Criterion,
    genomes: Sequence[str],
    reading: GenomeReading,
    count: int | None,
    noun: str,
) -> TypedOption:
    group = GenomeGroup(reading=reading, genomes=tuple(genomes))
    words = group.built_words.capitalize()
    label = words if count is None else f"{words} ({counted(count, noun)})"
    return TypedOption(
        id=option_id(label),
        label=label,
        binding=ReadGenomes(criterion_id=criterion.id, group=group),
    )


def _question(criterion: Criterion, noun: str) -> SlotQuestion:
    genomes = required_genomes(criterion)
    return SlotQuestion(
        question=(
            f"This step requires an ortholog in each of {len(genomes)} genomes: "
            f"{criterion.text}. Which reading should it build?"
        ),
        dimension=ConstraintKind.ORTHOLOG,
        criterion_id=criterion.id,
        param_name=INCLUDED_SPECIES,
        typed_options=[
            _option(
                criterion,
                genomes,
                "at_least_one",
                _at_least_one_count(_read(criterion)),
                noun,
            ),
            _option(criterion, genomes, "all", criterion.result_count, noun),
        ],
    )


def genome_reading_questions(spec: OperationalSpec, *, noun: str) -> list[SlotQuestion]:
    named = structure_criteria(spec.structure)
    return [_question(c, noun) for c in spec.criteria if _asks(c, named)]
