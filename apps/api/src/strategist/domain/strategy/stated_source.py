from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from strategist.domain.strategy.named_taxa import NamedTaxon

UnstatedSource = Literal["chosen", "default", "card", "held"]


class StatedSource(CamelModel):
    model_config = ConfigDict(frozen=True)

    words: str
    taxon: NamedTaxon | None = None


def sourced_fields(
    source: UnstatedSource | StatedSource, basis: str
) -> dict[str, object]:
    match source:
        case StatedSource(words=words, taxon=taxon):
            return {"source": "stated", "basis": words, "taxon": taxon}
        case "chosen" | "default" | "card" | "held":
            return {"source": source, "basis": basis, "taxon": None}
        case _:
            msg = f"{source!r} is no source a value takes outside value_source"
            raise ValueError(msg)
