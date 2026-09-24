"""Curation: a staged candidate becomes a corpus case, and stops being anybody's.

Promotion writes the case file first, then ends the association. If the write
fails there is still a staged row; if the update fails there is a case file and
a staged row a second promotion refuses by name.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.extract import EvalExtract
from pathfinder.evals.store import write_case
from pathfinder.persistence.models import EvalStagedCase
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository


class PromotionEdits(CamelModel):
    """What the curator decides. The turns and the expectation are theirs."""

    model_config = ConfigDict(frozen=True)

    name: str
    rationale: str
    turns: list[str] | None = None
    expected: ExpectedOutcome | None = None
    curator_note: str = ""


def staged_extract(row: EvalStagedCase) -> EvalExtract:
    """The extract of a staged row, or a failure when the row was promoted."""
    if row.extract is None:
        msg = f"staged case {row.id} holds no extract; it is already promoted"
        raise ValueError(msg)
    return EvalExtract.model_validate(row.extract)


def default_expectation(extract: EvalExtract) -> ExpectedOutcome:
    """What the recorded run did, as the expectation a curator starts from."""
    strategy = extract.strategy
    verification = extract.verification
    return ExpectedOutcome(
        builds_strategy=strategy is not None,
        structure=None if strategy is None else strategy.structure,
        step_count=None if strategy is None else strategy.step_count,
        verified=None if verification is None else verification.passed,
    )


def build_case(
    row: EvalStagedCase,
    edits: PromotionEdits,
    *,
    today: str | None = None,
) -> EvalCase:
    """The case a promotion writes, from the staged extract plus the edits."""
    extract = staged_extract(row)
    turns = edits.turns or [turn.request for turn in extract.turns]
    return EvalCase(
        name=edits.name,
        turns=turns,
        site_id=row.site_id,
        assistant_id=row.assistant_id,
        rationale=edits.rationale,
        expected=edits.expected or default_expectation(extract),
        provenance=CaseProvenance(
            site=row.site_id,
            assistant=row.assistant_id,
            origin="promoted",
            staging_id=str(row.id),
            added_at=today or datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
            curator_note=edits.curator_note,
        ),
    )


async def promote_staged_case(
    *,
    staging: EvalStagingRepository,
    staging_id: UUID,
    edits: PromotionEdits,
    directory: Path | None = None,
) -> Path:
    """Write the case file, then end the association. Returns the file."""
    row = await staging.get(staging_id)
    if row is None:
        msg = f"no staged case {staging_id}"
        raise LookupError(msg)
    path = write_case(build_case(row, edits), directory=directory)
    await staging.promote(staging_id=staging_id, corpus_name=edits.name)
    return path


__all__ = [
    "PromotionEdits",
    "build_case",
    "default_expectation",
    "promote_staged_case",
    "staged_extract",
]
