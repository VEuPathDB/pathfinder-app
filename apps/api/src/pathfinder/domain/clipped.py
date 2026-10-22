from __future__ import annotations

from pydantic import AfterValidator


def text_clipped_to(limit: int) -> AfterValidator:
    def clip(text: str) -> str:
        return text[:limit]

    return AfterValidator(clip)


def list_clipped_to(limit: int) -> AfterValidator:
    def clip[T](items: list[T]) -> list[T]:
        return items[:limit]

    return AfterValidator(clip)


def number_at_least(floor: int) -> AfterValidator:
    def clip(number: int) -> int:
        return max(number, floor)

    return AfterValidator(clip)
