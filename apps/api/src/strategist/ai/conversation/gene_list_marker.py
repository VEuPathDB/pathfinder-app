"""The text a message carries for an attached gene-id list.

The browser's attachment adapter writes the same two sentences.
"""

from __future__ import annotations

from typing import Final

GENE_LIST_PREFIX: Final = "Attached gene-ID list from"


def gene_list_marker(file_name: str, gene_ids: list[str]) -> str:
    """The sentence that stands for the file in the message."""
    if not gene_ids:
        return f"Attached file {file_name} contained no recognizable gene IDs."
    return f"{GENE_LIST_PREFIX} {file_name}: {', '.join(gene_ids)}"


__all__ = ["GENE_LIST_PREFIX", "gene_list_marker"]
