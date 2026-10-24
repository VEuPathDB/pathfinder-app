"""The review VERIFY returns, held to the record of the turn.

The structure check and the words no search states are the code's, so their
rows stand whatever the checker wrote. The column fits are the reads' own. A
sampled gene and a source stand only when a read of this turn returned them.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.evidence import RequirementCheck, SampledGene, VerificationReview
from pathfinder.domain.strategy.combination_check import (
    first_combination_violation,
    match_terms,
)
from pathfinder.domain.strategy.constraints import (
    GENE_ANSWERING_CLASSES,
    GENE_RECORD_NOUNS,
    CombinationRequest,
    Constraint,
    ConstraintKind,
    combination_requirements_from,
    record_noun,
)
from pathfinder.domain.strategy.message_reading import (
    message_states_constraint,
)
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    structure_criteria,
)
from pathfinder.domain.strategy.requirement_reports import RecordRole
from pathfinder.domain.strategy.step_rationale import names_the_phrase
from pathfinder.domain.strategy.words import whole_run_of

# The most step ids one requirement row names.
_ANSWERED_LIMIT = 8


@dataclass(frozen=True)
class ReviewRecord:
    """What the turn holds that a review is checked against."""

    # Every message the researcher wrote for the request, oldest first.
    messages: Sequence[str]
    requirements: Sequence[Constraint]
    spec: OperationalSpec | None
    # The form a read of this turn returned a reference in, else None.
    read_as: Callable[[str], str | None]
    # The page a read of one gene's record records.
    record_url: Callable[[str], str]
    class_names: Mapping[str, Collection[str]]
    record_roles: Mapping[str, RecordRole]
    # The columns this turn's reads measured on the strategy's live steps.
    column_fits: Sequence[ColumnFit] = ()


def _turn_where(messages: Sequence[str], stated: Callable[[str], bool]) -> int:
    """The first message that states it, else the latest message."""
    found = next((i for i, text in enumerate(messages, 1) if stated(text)), None)
    return found if found is not None else max(len(messages), 1)


@dataclass(frozen=True)
class _Breach:
    """A stated combination the structure contradicts, and the criteria its
    terms name."""

    row: RequirementCheck
    criteria: frozenset[str]


def _breaches(
    messages: Sequence[str],
    requirements: Sequence[Constraint],
    spec: OperationalSpec | None,
) -> list[_Breach]:
    if spec is None or spec.structure is None:
        return []
    found: list[_Breach] = []
    for constraint in combination_requirements_from(requirements):
        breach = first_combination_violation(
            [constraint], spec.criteria, spec.structure
        )
        request = CombinationRequest.parse(constraint.requested_value)
        if breach is None or request is None:
            continue
        matched = match_terms(request.terms, spec.criteria)
        row = RequirementCheck(
            text=constraint.requested_value,
            turn=_turn_where(
                messages,
                partial(message_states_constraint, constraint=constraint),
            ),
            how="structure",
            status="unmet",
            note=breach.message,
        )
        members = frozenset(matched.members.values()) if matched else frozenset()
        found.append(_Breach(row=row, criteria=members))
    return found


def breached_rows(
    messages: Sequence[str],
    requirements: Sequence[Constraint],
    spec: OperationalSpec | None,
) -> list[RequirementCheck]:
    """One unmet row per stated combination the structure contradicts. The
    strategy joins the steps another way, so no step answers the row; its
    note names the join."""
    return [breach.row for breach in _breaches(messages, requirements, spec)]


def _with_the_structure(
    rows: list[RequirementCheck], record: ReviewRecord
) -> list[RequirementCheck]:
    """The checker's rows, with each breached combination stated unmet."""
    breaches = _breaches(record.messages, record.requirements, record.spec)
    replaced = {cid for breach in breaches for cid in breach.criteria}
    stated = {breach.row.text for breach in breaches}
    kept = [
        row
        for row in rows
        if not (
            row.how == "structure"
            and (replaced.intersection(row.answered_by) or row.text in stated)
        )
    ]
    return [*kept, *(breach.row for breach in breaches)]


def _unexpressed_note(word: str) -> str:
    return f"no search the framing pass read can state '{word}'"


def _with_the_unexpressed(
    rows: list[RequirementCheck], record: ReviewRecord
) -> list[RequirementCheck]:
    """The rows, with every word no search states reported as unexpressed."""
    unexpressed = record.spec.unexpressed() if record.spec is not None else []
    held = list(rows)
    for text in unexpressed:
        word = text.word
        naming = [i for i, row in enumerate(held) if names_the_phrase(row.text, word)]
        for index in naming:
            if held[index].status == "met":
                held[index] = held[index].model_copy(
                    update={"status": "unexpressed", "note": _unexpressed_note(word)}
                )
        if naming:
            continue
        held.append(
            RequirementCheck(
                text=word,
                turn=_turn_where(
                    record.messages, partial(names_the_phrase, phrase=word)
                ),
                answered_by=[text.criterion_id] if text.criterion_id else [],
                how="search",
                status="unexpressed",
                note=_unexpressed_note(word),
            )
        )
    return held


def _class_words(record_class: str, names: Collection[str]) -> set[str]:
    return {word for name in [record_class, *names] if (word := record_noun(name))}


def _classes_named(text: str, record: ReviewRecord) -> set[str]:
    noun = record_noun(text)
    named = {
        record_class
        for record_class, names in record.class_names.items()
        if any(whole_run_of(noun, word) for word in _class_words(record_class, names))
    }
    if GENE_RECORD_NOUNS.intersection(noun.split()):
        named |= GENE_ANSWERING_CLASSES
    return named


def _names_the_same_classes(text: str, value: str, record: ReviewRecord) -> bool:
    if record_noun(text) == record_noun(value):
        return True
    named = _classes_named(text, record)
    return bool(named) and named == _classes_named(value, record)


def _stated_by(text: str, record: ReviewRecord) -> Constraint | None:
    return next(
        (
            c
            for c in record.requirements
            if c.kind == ConstraintKind.RECORD_TYPE
            and _names_the_same_classes(text, c.requested_value, record)
        ),
        None,
    )


def _a_bare_class(text: str, record: ReviewRecord) -> bool:
    noun = record_noun(text)
    return bool(noun) and noun in GENE_RECORD_NOUNS | {
        word
        for record_class, names in record.class_names.items()
        for word in _class_words(record_class, names)
    }


def _judged_against_the_root(
    row: RequirementCheck, spec: OperationalSpec, named: set[str]
) -> RequirementCheck:
    root = spec.record_type
    if root is None:
        note = "the strategy's record class is not known"
    else:
        note = f"the strategy returns {counted_noun(root)}s"
    if root is not None and root in named:
        ids = [c.id for c in spec.criteria][:_ANSWERED_LIMIT]
        return row.model_copy(
            update={"status": "met", "answered_by": ids, "note": note}
        )
    return row.model_copy(update={"status": "unmet", "answered_by": [], "note": note})


def _judged_against_the_steps(
    row: RequirementCheck, spec: OperationalSpec, named: set[str]
) -> RequirementCheck:
    tree = structure_criteria(spec.structure)
    through = [c for c in spec.criteria if c.id in tree and c.record_class in named]
    if not through:
        return row.model_copy(
            update={
                "status": "unmet",
                "answered_by": [],
                "note": f"no step of the strategy returns {row.text}",
            }
        )
    passed = counted_noun(through[0].record_class)
    return row.model_copy(
        update={
            "status": "met",
            "answered_by": [c.id for c in through][:_ANSWERED_LIMIT],
            "note": f"a step of the strategy returns {passed}s",
        }
    )


def _with_the_record_type(
    rows: list[RequirementCheck], record: ReviewRecord
) -> list[RequirementCheck]:
    """The rows, with each record-class row judged by the record class it names:
    an answer class against the class the strategy returns, and a class the
    strategy passes through against the classes its steps return."""
    spec = record.spec
    if spec is None or not spec.criteria:
        return rows
    held: list[RequirementCheck] = []
    for row in rows:
        stated = _stated_by(row.text, record)
        if stated is None and not _a_bare_class(row.text, record):
            held.append(row)
            continue
        role = "answer" if stated is None else record.record_roles.get(stated.key)
        named = _classes_named(row.text, record)
        judge = (
            _judged_against_the_steps if role == "through" else _judged_against_the_root
        )
        held.append(judge(row, spec, named))
    return held


def _read_genes(
    genes: Iterable[SampledGene], record: ReviewRecord
) -> list[SampledGene]:
    return [
        gene
        for gene in genes
        if record.read_as(record.record_url(gene.gene_id)) is not None
    ]


def review_held_to_the_turn(
    review: VerificationReview, record: ReviewRecord
) -> VerificationReview:
    """The review as the record lets it stand."""
    rows = _with_the_record_type(
        _with_the_unexpressed(
            _with_the_structure(list(review.requirements), record), record
        ),
        record,
    )
    return review.model_copy(
        update={
            "requirements": rows,
            "column_fits": list(record.column_fits),
            "sampled_genes": _read_genes(review.sampled_genes, record),
            "sources": [
                cited
                for cited in review.sources
                if all(record.read_as(ref) is not None for ref in cited.references())
            ],
        }
    )


__all__ = ["ReviewRecord", "breached_rows", "review_held_to_the_turn"]
