"""Where each gene of a saved set lives, and which of its ids another site reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import ConfigDict
from veupathdb.model import CamelModel

type SiteKind = Literal["genomics", "portal", "orthomcl"]


class GeneHome(CamelModel):
    """The gene a saved id names, by its id on the genomics site that holds it."""

    model_config = ConfigDict(frozen=True)

    gene_id: str
    site_id: str


def genes_on(
    origin: str,
    saved: Sequence[str],
    homes: Mapping[str, GeneHome],
    *,
    site_id: str,
    kind: SiteKind,
) -> list[str]:
    """The ids of a set that ``site_id`` reads. Its own site reads the ids as
    saved; the portal and OrthoMCL read every gene; a genomics site reads its own."""
    if site_id == origin:
        return list(saved)
    placed = [homes[s] for s in saved if s in homes]
    if kind != "genomics":
        return list(dict.fromkeys(home.gene_id for home in placed))
    return list(
        dict.fromkeys(home.gene_id for home in placed if home.site_id == site_id)
    )


__all__ = ["GeneHome", "SiteKind", "genes_on"]
