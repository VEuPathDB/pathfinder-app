"""The review VERIFY returns, held to the record of the turn.

The structure check and the words no search states are the code's, so their
rows stand whatever the checker wrote. The column fits are the reads' own. A
sampled gene and a source stand only when a read of this turn returned them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial

from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.evidence import (
    ColumnFit,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.strategy.combination_check import (
    first_combination_violation,
    match_terms,
)
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    combination_requirements_from,
    message_states_constraint,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.step_rationale import names_the_phrase


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
    # The columns this turn's reads measured on the strategy's live steps.
    column_fits: Sequence[ColumnFit] = ()


def _turn_where(messages: Sequence[str], stated: Callable[[str], bool]) -> int:
    """The first message that states it, else the latest message."""
    found = next((i for i, text in enumerate(messages, 1) if stated(text)), None)
    return found if found is not None else max(len(messages), 1)


def breached_rows(record: ReviewRecord) -> list[RequirementCheck]:
    """One unmet row per stated combination the structure contradicts."""
    spec = record.spec
    if spec is None or spec.structure is None:
        return []
    rows: list[RequirementCheck] = []
    for constraint in combination_requirements_from(record.requirements):
        breach = first_combination_violation(
            [constraint], spec.criteria, spec.structure
        )
        request = CombinationRequest.parse(constraint.requested_value)
        if breach is None or request is None:
            continue
        matched = match_terms(request.terms, spec.criteria)
        rows.append(
            RequirementCheck(
                text=constraint.requested_value,
                turn=_turn_where(
                    record.messages,
                    partial(message_states_constraint, constraint=constraint),
                ),
                answered_by=sorted(set(matched.members.values())) if matched else [],
                how="structure",
                status="unmet",
                note=breach.message,
            )
        )
    return rows


def _with_the_structure(
    rows: list[RequirementCheck], record: ReviewRecord
) -> list[RequirementCheck]:
    """The checker's rows, with each breached combination stated unmet."""
    breached = breached_rows(record)
    replaced = {cid for row in breached for cid in row.answered_by}
    kept = [
        row
        for row in rows
        if not (row.how == "structure" and replaced.intersection(row.answered_by))
    ]
    return [*kept, *breached]


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


def _with_the_record_type(
    rows: list[RequirementCheck], record: ReviewRecord
) -> list[RequirementCheck]:
    """The rows, with a stated record type met when the site counts the
    strategy's record class in that noun."""
    spec = record.spec
    if spec is None or not spec.criteria:
        return rows
    noun = counted_noun(spec.record_type)
    counted = {
        c.requested_value.casefold()
        for c in record.requirements
        if c.kind == ConstraintKind.RECORD_TYPE
        and c.requested_value.casefold() in {noun, f"{noun}s"}
    }
    return [
        row.model_copy(
            update={
                "status": "met",
                "answered_by": [c.id for c in spec.criteria][:_ANSWERED_LIMIT],
                "note": f"the strategy returns {noun}s",
            }
        )
        if row.text.casefold() in counted
        else row
        for row in rows
    ]


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
