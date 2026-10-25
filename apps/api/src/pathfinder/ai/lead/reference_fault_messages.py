"""The rewrite a refused reply is told for a reference that renders no answer
about the result, a value of a list, or a count beside words that repeat it."""

from __future__ import annotations

from pathfinder.domain.reply_references import ProseFault


def reference_sentence(fault: ProseFault) -> str | None:
    if fault.kind == "tally_of_a_step":
        return (
            f"``{fault.token}`` counts a step that is not the strategy's result, as "
            "its tally's title says, so it states nothing about the result: count "
            "the result step with count_step_by_column and cite that tally, or take "
            "it out."
        )
    if fault.kind == "listed_value":
        return (
            f"``{fault.token}`` is one of the values ``{fault.references[0]}`` "
            "holds, and that reference renders every one of them, so no reference "
            "renders it alone: cite it through a fact that holds it alone, or take "
            "it out."
        )
    if fault.kind == "zero_word":
        return (
            f"``{fault.token}``: ``{fault.references[0]}`` renders 0 with its noun, "
            "so write no word for none before it: 'the result holds [root]', not "
            "'the result is empty [root]'."
        )
    if fault.kind == "values_without_noun":
        return (
            f"``{fault.token}`` renders a number alone, so name its values after "
            "it: 'across [tally:<id>:values] organisms'."
        )
    return None


__all__ = ["reference_sentence"]
