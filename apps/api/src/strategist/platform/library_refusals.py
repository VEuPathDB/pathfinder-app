"""The problems a VEuPathDB library refusal names, one per row it reports."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, field_validator
from veupathdb.errors import VEuPathDBError

from strategist.domain.refusal import Problem, Problems, RefusalKey


class FaultRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    param: str = ""
    detail: str = ""
    value: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _a_term(cls, value: object) -> object:
        match value:
            case str():
                return value
            case _:
                return ""


_FAULT_ROWS = TypeAdapter(list[FaultRow])


def library_rows(error: VEuPathDBError[Any]) -> list[FaultRow]:
    return _FAULT_ROWS.validate_python(error.errors or [])


def library_problems(error: VEuPathDBError[Any], key: RefusalKey) -> Problems:
    said = error.detail or error.title
    rows = library_rows(error)
    if not rows:
        return Problems.one(key, said)
    return Problems(
        found=tuple(
            Problem(
                key=key.model_copy(update={"parameter": row.param}),
                sentence=row.detail or said,
            )
            for row in rows
        )
    )


__all__ = ["FaultRow", "library_problems", "library_rows"]
