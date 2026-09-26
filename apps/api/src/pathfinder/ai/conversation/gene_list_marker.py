"""The text a message carries for an attached gene-id list, written and read here.

The browser's attachment adapter writes the same two sentences.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_LISTED = "Attached gene-ID list from"


class ParsedGeneList(BaseModel):
    """The file a gene-id list came from and the ids it carried."""

    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    gene_ids: list[str] = Field(min_length=1)


def gene_list_marker(file_name: str, gene_ids: list[str]) -> str:
    """The sentence that stands for the file in the message."""
    if not gene_ids:
        return f"Attached file {file_name} contained no recognizable gene IDs."
    return f"{_LISTED} {file_name}: {', '.join(gene_ids)}"


def parse_gene_list_marker(text: str) -> ParsedGeneList | None:
    """The first list the text carries, or None when it carries no list."""
    start = text.find(_LISTED)
    if start == -1:
        return None
    file_name, colon, rest = text[start + len(_LISTED) :].partition(":")
    line = rest.splitlines()[0] if rest.strip() else ""
    gene_ids = [token.strip() for token in line.split(",") if token.strip()]
    if not colon or not file_name.strip() or not gene_ids:
        return None
    return ParsedGeneList(file_name=file_name.strip(), gene_ids=gene_ids)


__all__ = ["ParsedGeneList", "gene_list_marker", "parse_gene_list_marker"]
