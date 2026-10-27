"""The rewrite a refused reply is told for a list item named by a value, or a
row its fact does not hold."""

from __future__ import annotations

from pathfinder.domain.reply_references import ProseFault


def list_sentence(fault: ProseFault) -> str | None:
    if fault.kind == "misnamed_reference":
        written = " or ".join(f"``{r}``" for r in fault.references)
        return (
            f"``{fault.token}`` names no row of its fact: write {written}, the "
            "row of that name it holds."
        )
    if fault.kind == "keyed_reference":
        written = " or ".join(f"``{r}``" for r in fault.references)
        return (
            f"``{fault.token}`` names a list item by a value it holds, and a row "
            f"names each item by its place in the list: write {written}, which "
            "renders it."
        )
    return None


__all__ = ["list_sentence"]
