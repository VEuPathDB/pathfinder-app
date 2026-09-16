"""The arguments the Lead's scripted calls carry.

The arcs that make the calls live in ``arcs``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


_ATTACHMENT_MARKER = "Attached gene-ID list from"


class AttachedGeneList(BaseModel):
    """The file an attachment came from and the gene ids it carried."""

    source_name: str
    gene_ids: list[str]

    @property
    def control_set_name(self) -> str:
        """Name the control set after the file, so two uploads stay apart."""
        return f"Controls from {self.source_name}"


def attached_gene_list(text: str) -> AttachedGeneList | None:
    """Pull the file name and the cleaned gene IDs the composer's attachment
    adapter inlined as ``Attached gene-ID list from <name>: ID, ID, ...``
    (plain framing so the input injection scanner doesn't flag it)."""
    marker = text.find(_ATTACHMENT_MARKER)
    if marker == -1:
        return None
    colon = text.find(":", marker)
    if colon == -1:
        return None
    source_name = text[marker + len(_ATTACHMENT_MARKER) : colon].strip()
    line = text[colon + 1 :].splitlines()[0]
    gene_ids = [token.strip() for token in line.split(",") if token.strip()]
    if not source_name or not gene_ids:
        return None
    return AttachedGeneList(source_name=source_name, gene_ids=gene_ids)
