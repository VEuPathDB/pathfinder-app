from __future__ import annotations

import re
from collections.abc import Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from strategist.domain.turn_facts import TurnFacts

_DOI = re.compile(
    r"^(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.IGNORECASE
)
_PMID = re.compile(r"^(?:pmid:)?(\d{1,9})$", re.IGNORECASE)
_WEB = re.compile(r"^https?://\S+$", re.IGNORECASE)


class ReplyLinks(CamelModel):
    model_config = ConfigDict(frozen=True)

    links: list[str] = Field(default_factory=list)


def reference_urls(reference: str) -> list[str]:
    text = reference.strip()
    found = [text] if _WEB.match(text) else []
    if doi := _DOI.match(text):
        found.append(f"https://doi.org/{doi.group(1)}")
    elif pmid := _PMID.match(text):
        found.append(f"https://pubmed.ncbi.nlm.nih.gov/{pmid.group(1)}/")
    return list(dict.fromkeys(found))


def reply_links(facts: TurnFacts, retrieved: Sequence[str]) -> ReplyLinks:
    records = [source.url for source in facts.citable_records()]
    sources = [url for reference in retrieved for url in reference_urls(reference)]
    return ReplyLinks(links=list(dict.fromkeys([*records, *sources])))


__all__ = ["ReplyLinks", "reference_urls", "reply_links"]
