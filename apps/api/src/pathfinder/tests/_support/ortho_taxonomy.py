"""OrthoMCL's taxonomy as the client recorded it on QA."""

from __future__ import annotations

from veupathdb.domain.parameters import PhyleticTree
from veupathdb.wdk import WDKAnswer, ortho_taxonomy_of

from pathfinder.tests._support.qa_recording import client_recording


def recorded_ortho_taxonomy() -> PhyleticTree:
    tree = ortho_taxonomy_of(
        WDKAnswer.model_validate(client_recording("orthomcl_taxonomy").body)
    )
    assert tree is not None
    return tree


def labelled_genomes(tree: PhyleticTree, prefix: str) -> list[str]:
    return [n.code for n in tree.nodes() if not n.clade and n.label.startswith(prefix)]
