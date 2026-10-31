"""The values one parameter proposal names."""

from __future__ import annotations


def proposal_values(proposal: str | list[str] | None) -> list[str]:
    """The values one parameter proposal names: none, one, or a list."""
    match proposal:
        case None:
            return []
        case str():
            return [proposal]
        case list():
            return proposal


__all__ = ["proposal_values"]
