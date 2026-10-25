"""The rewrite a refused reply is told for a list item named by a value, or a
disputed finding of a run it reads and leaves unnamed."""

from __future__ import annotations

from pathfinder.domain.reply_references import ProseFault


def list_sentence(fault: ProseFault) -> str | None:
    if fault.kind == "unnamed_dispute":
        return (
            f"``{fault.token}``: the two reviews of this finding disagree, and a "
            "reply that reads this run names each disputed finding: name its genes "
            f"by their record references and write ``{fault.references[0]}`` after "
            "your words for the disagreement."
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
