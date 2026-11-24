"""The typed value a card answer's words state on a single-valued dimension."""

from __future__ import annotations

import re

from strategist.domain.strategy.constraints import (
    ConstraintKind,
    DataTypeValue,
    FoldChangeValue,
    PercentileValue,
    RequirementValue,
    SignificanceValue,
)

_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")
_LETTERS = re.compile(r"[^a-z0-9]")
_PERCENT = 100.0


def _number(words: str) -> float | None:
    found = _NUMBER.search(words)
    return None if found is None else float(found.group(1))


def _data_type(folded: str) -> DataTypeValue | None:
    letters = _LETTERS.sub("", folded)
    if "rnaseq" in letters:
        return DataTypeValue(data="rna_seq")
    return DataTypeValue(data="microarray") if "microarray" in letters else None


def _fold(folded: str, number: float) -> FoldChangeValue | None:
    if "log" in folded:
        return FoldChangeValue(cut=number, scale="log2")
    return FoldChangeValue(cut=number) if number > 0 else None


def stated_value(kind: ConstraintKind, words: str) -> RequirementValue | None:
    """The value of ``kind`` the words name, or None when they name none."""
    folded = words.casefold()
    number = _number(words)
    match kind:
        case ConstraintKind.PERCENTILE if number is not None and 0 < number <= _PERCENT:
            end = "bottom" if "bottom" in folded else "top"
            return PercentileValue(end=end, share=number)
        case ConstraintKind.FOLD_CHANGE if number is not None:
            return _fold(folded, number)
        case ConstraintKind.STATISTICAL_THRESHOLD if (
            number is not None and 0 < number <= 1
        ):
            return SignificanceValue(at_most=number)
        case ConstraintKind.DATA_TYPE:
            return _data_type(folded)
        case _:
            return None


__all__ = ["stated_value"]
