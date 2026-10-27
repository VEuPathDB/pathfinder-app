"""The rewrite a refused reply is told for a value of a list."""

from __future__ import annotations

from pathfinder.domain.reply_references import ProseFault


def reference_sentence(fault: ProseFault) -> str | None:
    if fault.kind == "listed_value":
        return (
            f"``{fault.token}`` is one of the values ``{fault.references[0]}`` "
            "holds, and that reference renders every one of them, so no reference "
            "renders it alone: cite it through a fact that holds it alone, or take "
            "it out."
        )
    return None


__all__ = ["reference_sentence"]
