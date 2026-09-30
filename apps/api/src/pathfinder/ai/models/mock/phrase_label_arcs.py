"""The canned spec of a text step on a search whose fields depend on its
document type, on an organism the message names one letter off."""

from __future__ import annotations

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec, SpecPlan, leaf

TEXT = "GenesByText"
MURIS = "Giardia muris strain Roberts-Thomson"
PHRASE = "cysteine-rich protein"
FIELDS = ("product", "Products", "Notes")


def muris_phrase_spec(values: SiteValues) -> SpecPlan:
    """One unquoted product text step on Giardia muris."""
    text = CriterionSpec(
        criterion_id="cysteine_rich_text",
        text=f"Giardia muris genes with a {PHRASE} annotation",
        search_name=TEXT,
        values={
            "text_search_organism": [MURIS],
            "document_type": "gene",
            "text_expression": PHRASE,
            "text_fields": list(FIELDS),
        },
    )
    return SpecPlan(
        title=f"Giardia muris {PHRASE} genes on {values.site_id}",
        criteria=(text,),
        structure=leaf(text),
    )


__all__ = ["FIELDS", "MURIS", "PHRASE", "TEXT", "muris_phrase_spec"]
