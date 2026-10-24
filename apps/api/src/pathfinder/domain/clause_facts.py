from __future__ import annotations

from collections.abc import Callable, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict


class MetClause(CamelModel):
    model_config = ConfigDict(frozen=True)

    number: str
    requirement: str
    clause: str
    criterion_id: str

    @property
    def sentence(self) -> str:
        return (
            f"'{self.requirement}' is met by the term the bound expression states: "
            f"{self.clause}"
        )

    @property
    def reference(self) -> str:
        return f"[met:{self.number}]"

    def redacted(self, redact: Callable[[str], str]) -> MetClause:
        return self.model_copy(update={"requirement": redact(self.requirement)})


def met_sentence(clauses: Sequence[MetClause], number: str) -> str | None:
    return next((c.sentence for c in clauses if c.number == number), None)


__all__ = ["MetClause", "met_sentence"]
