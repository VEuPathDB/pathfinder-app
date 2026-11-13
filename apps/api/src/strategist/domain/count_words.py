"""A count as the words a facts row or a caveat shows it with."""


def counted(count: int, noun: str) -> str:
    """The count with thousands separators and its noun."""
    return f"{count:,} {noun}" if count == 1 else f"{count:,} {noun}s"
