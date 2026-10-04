"""Which of the genes a turn asked about one catalog search holds, which a
reply's record references render."""

from __future__ import annotations

from collections.abc import Callable

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.record_page import ListedRecord


class MembershipFact(CamelModel):
    """The asked genes in the order they were asked, each with its page, and
    which of them the search holds. An unread id lies past the capped read of
    the search, so the search may hold it."""

    model_config = ConfigDict(frozen=True)

    search_label: str
    records: list[ListedRecord] = Field(default_factory=list)
    held: list[str] = Field(default_factory=list)
    unread: list[str] = Field(default_factory=list)

    def not_held(self) -> list[str]:
        """The asked ids that the whole read of the search does not hold."""
        judged = {*self.held, *self.unread}
        return [r.record_id for r in self.records if r.record_id not in judged]

    def lines(self) -> list[str]:
        label = self.search_label
        rows = (
            (f"Held by {label}", self.held),
            (f"Not held by {label}", self.not_held()),
            (f"Past the read of {label}", self.unread),
        )
        return [f"{title}: {', '.join(ids)}" for title, ids in rows if ids]

    def redacted(self, redact: Callable[[str], str]) -> MembershipFact:
        return self.model_copy(update={"search_label": redact(self.search_label)})


__all__ = ["MembershipFact"]
