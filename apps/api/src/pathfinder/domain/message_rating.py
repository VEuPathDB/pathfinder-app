"""What a researcher's rating of one message does to the cases that message wrote."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from assistant_core.memory.autowrite import MemoryCandidate
from assistant_core.memory.schemas import MemoryValue
from pydantic import BaseModel, ConfigDict

type Rating = Literal["like", "dislike"]

CASE_KIND = "case"

# The tag the runtime's hybrid score reads as a pin.
PINNED_TAG = "pinned"


class StandingRating(BaseModel):
    """Another message's standing rating, and the case keys it governs."""

    model_config = ConfigDict(frozen=True)

    rating: Rating
    case_keys: tuple[str, ...]
    updated_at: datetime


class WithheldCase(BaseModel):
    """A case value a rating keeps out of the store, so it can be put back."""

    model_config = ConfigDict(frozen=True)

    key: str
    value: MemoryValue


@dataclass(frozen=True)
class CasePartition:
    """The candidates to write, and the case candidates to keep out of the store."""

    written: list[MemoryCandidate] = field(default_factory=list)
    withheld: list[MemoryCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class CaseMoves:
    """The store writes one rating asks for, and the values its row keeps."""

    put: list[MemoryCandidate] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    withheld: dict[str, MemoryValue] = field(default_factory=dict)


def pinned(value: MemoryValue) -> MemoryValue:
    if PINNED_TAG in value.tags:
        return value
    return value.model_copy(update={"tags": [*value.tags, PINNED_TAG]})


def unpinned(value: MemoryValue) -> MemoryValue:
    if PINNED_TAG not in value.tags:
        return value
    return value.model_copy(
        update={"tags": [tag for tag in value.tags if tag != PINNED_TAG]}
    )


def deciding_rating(
    key: str,
    *,
    own: Rating | None,
    others: Sequence[StandingRating],
) -> Rating | None:
    """The own message's rating, else the latest other rating that names the key."""
    if own is not None:
        return own
    holding = [other for other in others if key in other.case_keys]
    if not holding:
        return None
    return max(holding, key=lambda other: other.updated_at).rating


def _shaped(value: MemoryValue, rating: Rating | None) -> MemoryValue:
    return pinned(value) if rating == "like" else unpinned(value)


def partition_cases(
    candidates: Sequence[MemoryCandidate],
    *,
    own: Rating | None,
    others: Sequence[StandingRating],
) -> CasePartition:
    """Withhold a disliked case, pin a liked one, pass every other kind through."""
    parts = CasePartition()
    for value, key in candidates:
        if value.kind != CASE_KIND:
            parts.written.append((value, key))
            continue
        rating = deciding_rating(key, own=own, others=others)
        if rating == "dislike":
            parts.withheld.append((value, key))
        elif rating == "like":
            parts.written.append((pinned(value), key))
        else:
            parts.written.append((value, key))
    return parts


def settle_cases(
    *,
    case_keys: Sequence[str],
    stored: Mapping[str, MemoryValue],
    withheld: Mapping[str, MemoryValue],
    own: Rating | None,
    others: Sequence[StandingRating],
) -> CaseMoves:
    """Bring each case of one message into the shape its deciding rating asks for.

    A key with no stored and no withheld value is skipped: the researcher
    deleted that memory.
    """
    moves = CaseMoves()
    for key in case_keys:
        current = stored.get(key)
        value = current if current is not None else withheld.get(key)
        if value is None:
            continue
        rating = deciding_rating(key, own=own, others=others)
        if rating == "dislike":
            moves.withheld[key] = value
            if current is not None:
                moves.remove.append(key)
            continue
        shaped = _shaped(value, rating)
        if shaped != current:
            moves.put.append((shaped, key))
    return moves


__all__ = [
    "CASE_KIND",
    "PINNED_TAG",
    "CaseMoves",
    "CasePartition",
    "Rating",
    "StandingRating",
    "WithheldCase",
    "deciding_rating",
    "partition_cases",
    "pinned",
    "settle_cases",
    "unpinned",
]
