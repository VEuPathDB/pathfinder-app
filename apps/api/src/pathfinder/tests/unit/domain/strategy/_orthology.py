"""The measured round trip as specs and trees: a P. falciparum 3D7 seed of two
searches, carried to P. vivax P01 and back by the site's orthology transform."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)

SOURCE = "Plasmodium falciparum 3D7"
TARGET = "Plasmodium vivax P01"
ORTHOLOGS = "GenesByOrthologs"


def seed_criteria(signal_id: str = "c_signal", tm_id: str = "c_tm") -> list[Criterion]:
    organism = MultiPickValue(values=[SOURCE])
    return [
        Criterion(
            id=signal_id,
            text="predicted signal peptide",
            search_name="GenesWithSignalPeptide",
            search_display_name="Predicted Signal Peptide",
            role="seed",
            resolved_params={
                "organism": organism,
                "signalp_version": SinglePickValue(value="SignalP-6.0"),
            },
        ),
        Criterion(
            id=tm_id,
            text="2 to 99 transmembrane domains",
            search_name="GenesByTransmembraneDomains",
            search_display_name="Transmembrane Domain Count",
            resolved_params={
                "organism": organism,
                "min_tm": StringValue(value="2"),
                "max_tm": StringValue(value="99"),
            },
        ),
    ]


def leg(criterion_id: str, organism: str, syntenic: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"syntenic orthologs in {organism}",
        search_name=ORTHOLOGS,
        search_display_name="Transform by Orthology",
        role="transform",
        resolved_params={
            "organism": MultiPickValue(values=[organism]),
            "isSyntenic": SinglePickValue(value=syntenic),
        },
    )


def seed_node(signal_id: str = "c_signal", tm_id: str = "c_tm") -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(kind="leaf", criterion_id=signal_id),
            StructureNode(kind="leaf", criterion_id=tm_id),
        ],
    )


def trip(source: StructureNode) -> StructureNode:
    """Back to the source organism, over P. vivax P01, over ``source``."""
    there = StructureNode(kind="transform", criterion_id="c_to", inputs=[source])
    return StructureNode(kind="transform", criterion_id="c_back", inputs=[there])


def copy_of(node: StructureNode) -> StructureNode:
    return StructureNode(kind="copy", inputs=[node.model_copy(deep=True)])


def kept_by_intersect(seed: StructureNode) -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[seed, trip(copy_of(seed))],
    )


def round_trip_spec(
    root: StructureNode | None = None,
    *,
    back_syntenic: str = "yes",
    seed: list[Criterion] | None = None,
) -> OperationalSpec:
    """The seed INTERSECT its syntenic round trip, unless ``root`` says otherwise."""
    return OperationalSpec(
        goal="keep only those with syntenic orthologs in Plasmodium vivax P01",
        criteria=[
            *(seed if seed is not None else seed_criteria()),
            leg("c_to", TARGET, "yes"),
            leg("c_back", SOURCE, back_syntenic),
        ],
        structure=SpecStructure(root=root or kept_by_intersect(seed_node())),
    )
