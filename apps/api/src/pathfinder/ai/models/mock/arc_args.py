"""The arguments the Lead's scripted calls carry."""

from __future__ import annotations

from typing import Any


def _variant_text_params(expression: str, organism: str) -> dict[str, Any]:
    return {
        "text_expression": {"type": "string", "value": expression},
        "text_fields": {"type": "multi-pick-vocabulary", "values": ["product"]},
        "document_type": {"type": "string", "value": "gene"},
        "text_search_organism": {
            "type": "multi-pick-vocabulary",
            "values": [organism],
        },
    }


def variant_args(organism: str) -> dict[str, Any]:
    return {
        "variants": [
            {
                "label": "kinase",
                "search_name": "GenesByText",
                "parameters": _variant_text_params("kinase", organism),
            },
            {
                "label": "phosphatase",
                "search_name": "GenesByText",
                "parameters": _variant_text_params("phosphatase", organism),
            },
        ],
    }
