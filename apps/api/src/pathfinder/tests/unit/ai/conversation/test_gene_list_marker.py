"""The text a message carries for an attached gene-id list, written and read in one place."""

from __future__ import annotations

import re
from pathlib import Path

from pathfinder.ai.conversation.gene_list_marker import (
    ParsedGeneList,
    gene_list_marker,
    parse_gene_list_marker,
)

_ADAPTER_TEST = (
    Path(__file__).resolve().parents[8]
    / "apps"
    / "web"
    / "src"
    / "features"
    / "conversation"
    / "runtime"
    / "chatAttachmentAdapter.test.ts"
)


def _adapter_texts() -> list[str]:
    """Every gene-list sentence the browser adapter's tests expect it to write."""
    return re.findall(
        r'text: "(Attached (?:gene-ID list from|file) [^"]+)"',
        _ADAPTER_TEST.read_text(),
    )


def test_the_api_writes_the_sentences_the_browser_adapter_writes() -> None:
    assert _adapter_texts() == [
        gene_list_marker("controls.csv", ["PF3D7_0100100", "PF3D7_0200200"]),
        gene_list_marker("empty.csv", []),
    ]


def test_a_list_reads_back_as_its_file_and_its_ids() -> None:
    text = "Use these.\n\n" + gene_list_marker(
        "controls.csv", ["PF3D7_0709000", "PF3D7_1133400"]
    )

    assert parse_gene_list_marker(text) == ParsedGeneList(
        file_name="controls.csv", gene_ids=["PF3D7_0709000", "PF3D7_1133400"]
    )


def test_an_empty_list_and_a_plain_message_read_as_no_list() -> None:
    texts = [
        gene_list_marker("empty.csv", []),
        "Find kinases.",
        "Attached gene-ID list from",
    ]

    assert [parse_gene_list_marker(text) for text in texts] == [None, None, None]
