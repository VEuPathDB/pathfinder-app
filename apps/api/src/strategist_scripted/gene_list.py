from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from strategist.ai.conversation.gene_list_marker import GENE_LIST_PREFIX


class ParsedGeneList(BaseModel):
    """The file a gene-id list came from and the ids it carried."""

    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    gene_ids: list[str] = Field(min_length=1)


def parse_gene_list_marker(text: str) -> ParsedGeneList | None:
    """The first list the text carries, or None when it carries no list."""
    start = text.find(GENE_LIST_PREFIX)
    if start == -1:
        return None
    file_name, colon, rest = text[start + len(GENE_LIST_PREFIX) :].partition(":")
    line = rest.splitlines()[0] if rest.strip() else ""
    gene_ids = [token.strip() for token in line.split(",") if token.strip()]
    if not colon or not file_name.strip() or not gene_ids:
        return None
    return ParsedGeneList(file_name=file_name.strip(), gene_ids=gene_ids)
