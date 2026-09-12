"""The arguments the Lead's scripted calls carry.

The arcs that make the calls live in ``arcs``.
"""

from __future__ import annotations

from typing import Any


def _variant_text_params(expression: str) -> dict[str, Any]:
    return {
        "text_expression": {"type": "string", "value": expression},
        "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
        "document_type": {"type": "string", "value": "gene"},
        "text_search_organism": {
            "type": "multi-pick-vocabulary",
            "values": ["Plasmodium falciparum 3D7"],
        },
    }


def variant_args() -> dict[str, Any]:
    return {
        "variants": [
            {
                "label": "kinase",
                "search_name": "GenesByText",
                "record_type": "transcript",
                "parameters": _variant_text_params("kinase"),
            },
            {
                "label": "phosphatase",
                "search_name": "GenesByText",
                "record_type": "transcript",
                "parameters": _variant_text_params("phosphatase"),
            },
        ],
    }


def consult_args() -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": "q1",
                "prompt": "Fold-change threshold?",
                "kind": "single_choice",
                "options": [
                    {"label": "2-fold", "recommended": True},
                    {"label": "5-fold"},
                ],
            },
            {
                "id": "q2",
                "prompt": "Include the microarray arm?",
                "kind": "single_choice",
                "options": [{"label": "Yes"}, {"label": "No"}],
            },
        ],
    }


def attachment_gene_ids(text: str) -> list[str]:
    """Pull the cleaned gene IDs the composer's attachment adapter inlined as
    ``Attached gene-ID list from <name>: ID, ID, ...`` (plain framing so the
    input injection scanner doesn't flag it)."""
    marker = text.find("Attached gene-ID list from")
    if marker == -1:
        return []
    colon = text.find(":", marker)
    if colon == -1:
        return []
    line = text[colon + 1 :].splitlines()[0]
    return [token.strip() for token in line.split(",") if token.strip()]
