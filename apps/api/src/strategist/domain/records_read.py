from __future__ import annotations

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from strategist.domain.count_words import counted
from strategist.domain.site_checks import SiteCheck

_RECORDS = "the records of the result"


def records_read(tried: int, answered: int) -> SiteCheck:
    """Whether the check read a record of the result: unchecked when it read
    none, and blamed on the site only when every read it tried got no answer."""
    if answered:
        return SiteCheck(
            kind="records_read",
            subject=_RECORDS,
            status="pass",
            evidence=f"the check read records in {counted(answered, 'read')}",
        )
    if not tried:
        return SiteCheck(
            kind="records_read",
            subject=_RECORDS,
            status="unchecked",
            evidence="the check read no record of the result",
            why_unchecked="no_check",
        )
    return SiteCheck(
        kind="records_read",
        subject=_RECORDS,
        status="unchecked",
        evidence=(
            "no record was read: the site did not answer "
            f"{counted(tried, 'record read')}"
        ),
        why_unchecked="site_unanswered",
    )


class SampleReads(CamelModel):
    """The record reads one check tried and the ones the site answered."""

    model_config = ConfigDict(frozen=True)

    tried: int = 0
    answered: int = 0

    def check(self) -> SiteCheck:
        return records_read(self.tried, self.answered)
