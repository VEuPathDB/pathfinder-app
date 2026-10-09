"""The arguments the Lead's scripted calls carry."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from pathfinder.ai.models.mock.strategy_specs import SIGNAL_PEPTIDE

TEXT_SEARCH = "GenesByText"
SIGNALP_VERSIONS = ("SignalP-6.0", "SignalP-4.1")


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


def _signalp_params(version: str, organism: str) -> dict[str, Any]:
    return {
        "organism": {"type": "multi-pick-vocabulary", "values": [organism]},
        "signalp_version": {"type": "single-pick-vocabulary", "value": version},
    }


def variant_args(organism: str, searches: Collection[str]) -> dict[str, Any]:
    if TEXT_SEARCH not in searches:
        return {
            "variants": [
                {
                    "label": version,
                    "search_name": SIGNAL_PEPTIDE,
                    "parameters": _signalp_params(version, organism),
                }
                for version in SIGNALP_VERSIONS
            ],
        }
    return {
        "variants": [
            {
                "label": "kinase",
                "search_name": TEXT_SEARCH,
                "parameters": _variant_text_params("kinase", organism),
            },
            {
                "label": "phosphatase",
                "search_name": TEXT_SEARCH,
                "parameters": _variant_text_params("phosphatase", organism),
            },
        ],
    }
