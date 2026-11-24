"""The genomes a phylogenetic profile step's included species stand for."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import ParamValue, PhyleticTree, to_wire

from strategist.domain.strategy.genome_group import INCLUDED_SPECIES


def included_genomes(
    tree: PhyleticTree | None, params: Mapping[str, ParamValue]
) -> list[str]:
    """The name of each genome the included species codes cover, in tree order."""
    included = params.get(INCLUDED_SPECIES)
    if tree is None or included is None:
        return []
    genomes = tree.genomes_under(tree.resolve_terms(to_wire(included)).codes)
    return [node.label for node in tree.nodes() if node.code in genomes]


__all__ = ["included_genomes"]
