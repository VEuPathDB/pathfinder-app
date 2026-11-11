from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pathfinder.platform.tool_sources import RESEARCH_TOOL_SOURCE

RESEARCH_UNAVAILABLE: Final = (
    "## Literature and web search\n"
    "Literature and web search are unavailable this turn. When an answer needs a "
    "paper or a web page, say that you cannot search them now instead of answering "
    "from memory."
)


def research_served(sources: Mapping[str, object]) -> bool:
    return RESEARCH_TOOL_SOURCE.name in sources


def research_reads(reads: str, *, served: bool) -> str:
    return reads if served else RESEARCH_UNAVAILABLE
