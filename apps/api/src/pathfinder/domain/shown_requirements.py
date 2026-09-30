"""A requirement only a text query answers is held to the records a check
read: a text query matches words, never the thing the words name. A requirement
that names the researcher's upload is met by the step that runs on it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import message_states
from pathfinder.domain.strategy.words import FILLER_WORDS, words_of

_NOT_SHOWN = "the query text alone does not show it"
_UNJUDGED = f"no sampled record judged it; {_NOT_SHOWN}"


class TextQuery(BaseModel):
    """One free-text value a criterion binds."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    param: str
    value: str

    def states(self, text: str) -> bool:
        """Whether the value and the text share a word that is not filler."""
        own = set(words_of(self.value)) - FILLER_WORDS
        return bool(own & set(words_of(text)))


def _only_text_answers(row: RequirementCheck, queries: Sequence[TextQuery]) -> bool:
    """Whether a text value states the row and every answer of the row binds a
    text query."""
    by_criterion = {q.criterion_id for q in queries}
    return (
        bool(row.answered_by)
        and all(answer in by_criterion for answer in row.answered_by)
        and any(
            q.states(row.text) for q in queries if q.criterion_id in row.answered_by
        )
    )


def _shown(row: RequirementCheck, review: VerificationReview) -> bool:
    """Whether a record shows the row: a sampled gene judged to fit it, every
    sampled gene judged to fit, or a column every record of its step fits."""
    genes = {g.gene_id for g in review.sampled_genes if g.fits == "yes"}
    columns = {
        f.column
        for f in review.column_fits
        if f.fits == "all" and f.criterion_id in row.answered_by
    }
    every_sample_fits = bool(review.sampled_genes) and len(genes) == len(
        review.sampled_genes
    )
    return every_sample_fits or bool(set(row.shown_by) & (genes | columns))


def _shown_missing(
    row: RequirementCheck, review: VerificationReview, queries: Sequence[TextQuery]
) -> bool:
    """Whether a record shows the row missing: a sampled gene judged not to fit
    for a reason a text query of the row states, or a column of its criteria
    that some record falls outside. An unclear judgement shows nothing."""
    answering = [q for q in queries if q.criterion_id in row.answered_by]
    return any(
        g.fits == "no" and any(q.states(g.why) for q in answering)
        for g in review.sampled_genes
    ) or any(
        f.shown and f.fitting_at_most < f.total
        for f in review.column_fits
        if f.criterion_id in row.answered_by
    )


def _not_shown(review: VerificationReview) -> str:
    """Why the row stands unmet, with the share of sampled genes that fit."""
    sampled = len(review.sampled_genes)
    if not sampled:
        return f"no column fit or sampled record of this check shows it; {_NOT_SHOWN}"
    fitting = sum(g.fits == "yes" for g in review.sampled_genes)
    return (
        f"{fitting} of {sampled} sampled records fit and no column fit shows it; "
        f"{_NOT_SHOWN}"
    )


def _held(
    row: RequirementCheck, review: VerificationReview, queries: Sequence[TextQuery]
) -> RequirementCheck:
    """The row unmet when a record shows it missing, unjudged when no record
    judged it, else as the check filed it."""
    if (
        row.status != "met"
        or not _only_text_answers(row, queries)
        or _shown(row, review)
    ):
        return row
    if _shown_missing(row, review, queries):
        return row.model_copy(
            update={
                "status": "unmet",
                "note": _not_shown(review),
                "no_record_shows_it": True,
            }
        )
    return row.model_copy(update={"note": _UNJUDGED, "no_record_judged_it": True})


def held_to_the_records(
    review: VerificationReview, queries: Sequence[TextQuery]
) -> VerificationReview:
    """The review with each met row only a text query answers held to the
    records the check read. ``queries`` holds the text queries the spec binds."""
    rows = [_held(row, review, queries) for row in review.requirements]
    if rows == review.requirements:
        return review
    return review.model_copy(update={"requirements": rows})


def _on_the_upload(
    row: RequirementCheck, uploads: Mapping[str, str]
) -> RequirementCheck:
    runs_on = {c: name for c, name in uploads.items() if message_states(row.text, name)}
    if row.status == "met" or not runs_on:
        return row
    names = ", ".join(f"'{name}'" for name in dict.fromkeys(runs_on.values()))
    return row.model_copy(
        update={
            "status": "met",
            "answered_by": list(runs_on),
            "how": "parameter",
            "note": f"The step runs on the upload {names}.",
        }
    )


def answered_by_uploads(
    review: VerificationReview, uploads: Mapping[str, str]
) -> VerificationReview:
    """The review with each row that names an upload met by the criteria that
    run on it. ``uploads`` maps each criterion id to its upload's name."""
    rows = [_on_the_upload(row, uploads) for row in review.requirements]
    if rows == review.requirements:
        return review
    return review.model_copy(update={"requirements": rows})


__all__ = ["TextQuery", "answered_by_uploads", "held_to_the_records"]
