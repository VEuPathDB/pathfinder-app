from __future__ import annotations

import re
from typing import Annotated

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from veupathdb.model import CamelModel

_WHITESPACE = re.compile(r"\s+")


def _one_line(value: object) -> object:
    match value:
        case str():
            return _WHITESPACE.sub(" ", value).strip()
        case _:
            return value


Sentence = Annotated[str, BeforeValidator(_one_line), StringConstraints(min_length=1)]


class RefusalKey(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Annotated[str, StringConstraints(min_length=1)]
    criterion: str = ""
    search: str = ""
    parameter: str = ""

    def label(self) -> str:
        named = [part for part in (self.criterion, self.search, self.parameter) if part]
        return " / ".join(named) if named else self.check

    def __hash__(self) -> int:
        return hash((self.check, self.criterion, self.search, self.parameter))

    def under(self, *, criterion: str, search: str) -> RefusalKey:
        return self.model_copy(
            update={
                "criterion": self.criterion or criterion,
                "search": self.search or search,
            }
        )


class Problem(CamelModel):
    model_config = ConfigDict(frozen=True)

    key: RefusalKey
    sentence: Sentence

    def __hash__(self) -> int:
        return hash((self.key, self.sentence))


class Problems(CamelModel):
    model_config = ConfigDict(frozen=True)

    found: tuple[Problem, ...] = ()

    @field_validator("found", mode="after")
    @classmethod
    def _named_once(cls, found: tuple[Problem, ...]) -> tuple[Problem, ...]:
        return tuple(dict.fromkeys(found))

    @classmethod
    def one(cls, key: RefusalKey, sentence: str) -> Problems:
        return cls(found=(Problem(key=key, sentence=sentence),))

    def plus(self, more: Problems) -> Problems:
        return Problems(found=self.found + more.found)

    def under(self, *, criterion: str, search: str) -> Problems:
        return Problems(
            found=tuple(
                Problem(
                    key=p.key.under(criterion=criterion, search=search),
                    sentence=p.sentence,
                )
                for p in self.found
            )
        )

    @property
    def empty(self) -> bool:
        return not self.found

    def keys(self) -> tuple[RefusalKey, ...]:
        return tuple(dict.fromkeys(p.key for p in self.found))

    def text(self) -> str:
        if not self.found:
            return ""
        if len(self.found) == 1:
            return self.found[0].sentence
        lines = [f"{i}. {p.sentence}" for i, p in enumerate(self.found, start=1)]
        return "\n".join([f"{len(self.found)} problems:", *lines])


class KeyUse(CamelModel):
    model_config = ConfigDict(frozen=True)

    key: RefusalKey
    used: Annotated[int, Field(ge=1)]


class RefusalLedger(CamelModel):
    model_config = ConfigDict(frozen=True)

    uses: tuple[KeyUse, ...] = ()

    @field_validator("uses", mode="after")
    @classmethod
    def _one_row_per_key(cls, uses: tuple[KeyUse, ...]) -> tuple[KeyUse, ...]:
        if len({use.key for use in uses}) != len(uses):
            msg = "a refusal ledger holds one row per key"
            raise ValueError(msg)
        return uses

    def used(self, key: RefusalKey) -> int:
        return next((use.used for use in self.uses if use.key == key), 0)

    def charge(self, problems: Problems, per_key: int) -> Charge:
        named = problems.keys()
        live = tuple(key for key in named if self.used(key) < per_key)
        raised = tuple(
            KeyUse(key=use.key, used=use.used + 1) if use.key in live else use
            for use in self.uses
        )
        first = tuple(KeyUse(key=key, used=1) for key in live if self.used(key) == 0)
        return Charge(
            ledger=RefusalLedger(uses=raised + first),
            refused=Problems(found=tuple(p for p in problems.found if p.key in live)),
            spent=Problems(found=tuple(p for p in problems.found if p.key not in live)),
        )


class Charge(CamelModel):
    model_config = ConfigDict(frozen=True)

    ledger: RefusalLedger
    refused: Problems
    spent: Problems
