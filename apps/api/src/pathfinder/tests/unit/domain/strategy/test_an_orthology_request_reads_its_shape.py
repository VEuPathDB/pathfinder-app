"""The words of a message decide the orthology shape it asks for: a carry to an
organism is one transform, and a gene kept for its ortholog there is the round
trip. A tree of the other shape is refused, and unknown wording abstains."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology_request import (
    OrthologyRequest,
    orthology_shape_refusal,
)

from ._orthology import (
    SOURCE,
    TARGET,
    leg,
    round_trip_spec,
    seed_criteria,
    seed_node,
)

_ME49 = "Toxoplasma gondii ME49"


def test_a_carry_to_syntenic_orthologs_is_one_transform_to_the_organism() -> None:
    assert OrthologyRequest.read(
        f"Carry these to their syntenic orthologs in {_ME49}."
    ) == OrthologyRequest(shape="transform", target=_ME49)


@pytest.mark.parametrize(
    "message",
    [
        f"Map them to their orthologs in {_ME49}",
        f"Translate this list into its {_ME49} counterparts.",
        f"Move these genes over to the orthologs in {_ME49}, please.",
        f"OK. Now carry those 8 P. vivax P01 genes over to their orthologs in {_ME49}.",
    ],
)
def test_every_carry_verb_reads_a_transform(message: str) -> None:
    assert OrthologyRequest.read(message) == OrthologyRequest(
        shape="transform", target=_ME49
    )


def test_a_carry_that_names_no_organism_reads_no_target() -> None:
    assert OrthologyRequest.read(
        "Then carry them to their syntenic orthologs in a related species."
    ) == OrthologyRequest(shape="transform", target="")


def test_an_abbreviated_genus_is_the_target() -> None:
    assert OrthologyRequest.read(
        "Carry these to their T. gondii counterparts"
    ) == OrthologyRequest(shape="transform", target="T. gondii")


@pytest.mark.parametrize(
    ("message", "target"),
    [
        ("Keep only those with syntenic orthologs in Plasmodium vivax P01.", TARGET),
        (
            (
                "Give me Cryptosporidium parvum Iowa II genes that have an ortholog "
                "in Toxoplasma gondii but none in Homo sapiens."
            ),
            "Toxoplasma gondii",
        ),
        ("Which of them are conserved in T. gondii?", "T. gondii"),
        (f"keep only genes having an ortholog in {_ME49}", _ME49),
    ],
)
def test_a_gene_kept_for_its_ortholog_reads_the_round_trip(
    message: str, target: str
) -> None:
    assert OrthologyRequest.read(message) == OrthologyRequest(
        shape="round_trip", target=target
    )


@pytest.mark.parametrize(
    "message",
    [
        "Find kinases in Plasmodium falciparum 3D7.",
        "Move the GO step to the top of the strategy.",
        "Map these genes to their GO terms.",
        "Plasmodium knowlesi strain H genes that have no ortholog in Homo sapiens.",
        (
            f"Carry the genes that have an ortholog in {_ME49} to their orthologs "
            "in Neospora caninum Liverpool."
        ),
        (
            f"Carry these to their orthologs in {_ME49}, then carry those to their "
            "orthologs in Neospora caninum Liverpool."
        ),
    ],
)
def test_unknown_or_mixed_wording_reads_no_shape(message: str) -> None:
    assert [OrthologyRequest.read(message)] == [None]


def _one_way() -> OperationalSpec:
    return OperationalSpec(
        goal="carry these to their syntenic orthologs in Plasmodium vivax P01",
        criteria=[*seed_criteria(), leg("c_to", TARGET, "yes")],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform", criterion_id="c_to", inputs=[seed_node()]
            )
        ),
    )


_CARRY = OrthologyRequest(shape="transform", target=TARGET)
_KEEP = OrthologyRequest(shape="round_trip", target=TARGET)


def test_a_round_trip_for_a_carry_is_refused_with_the_transform_shape() -> None:
    assert orthology_shape_refusal(_CARRY, round_trip_spec(), held=frozenset()) == (
        f"The message carries the genes to {TARGET}, which asks for one transform "
        f"whose result is the genes of {TARGET}. c_back maps them back to "
        f"{SOURCE}, a round trip that keeps the source genes. State "
        '{"kind": "transform", "criterionId": "<the transform>", "inputs": '
        "[<the source subtree>]} with the organism the message names, and no "
        "transform back."
    )


def test_a_one_way_transform_for_a_kept_gene_is_refused_with_the_round_trip() -> None:
    assert orthology_shape_refusal(_KEEP, _one_way(), held=frozenset()) == (
        f"The message keeps the genes that have an ortholog in {TARGET}, which "
        f"asks for the round trip that keeps the source genes. c_to returns the "
        f"genes of {TARGET} where the source holds genes of {SOURCE}. State "
        '{"kind": "combine", "operator": "INTERSECT", "inputs": [<the source '
        "subtree>, <the transform back>]}, where the transform back to "
        f"{SOURCE} takes the transform to {TARGET} as its input, and the "
        f'transform to {TARGET} takes {{"kind": "copy", "inputs": [<the source '
        "subtree>]}."
    )


def test_the_shape_the_words_ask_for_is_kept() -> None:
    assert [
        orthology_shape_refusal(_CARRY, _one_way(), held=frozenset()),
        orthology_shape_refusal(_KEEP, round_trip_spec(), held=frozenset()),
    ] == [None, None]


def test_a_held_round_trip_stands_beside_a_carry() -> None:
    held = frozenset({"c_signal", "c_tm", "c_to", "c_back"})

    assert [orthology_shape_refusal(_CARRY, round_trip_spec(), held=held)] == [None]


def test_a_held_one_way_transform_stands_beside_a_kept_gene() -> None:
    held = frozenset({"c_signal", "c_tm", "c_to"})

    assert [orthology_shape_refusal(_KEEP, _one_way(), held=held)] == [None]


def test_a_carry_with_no_organism_names_another_organism() -> None:
    refusal = orthology_shape_refusal(
        OrthologyRequest(shape="transform"), round_trip_spec(), held=frozenset()
    )

    assert refusal == (
        "The message carries the genes to another organism, which asks for one "
        "transform whose result is the genes of that organism. c_back maps them "
        f"back to {SOURCE}, a round trip that keeps the source genes. State "
        '{"kind": "transform", "criterionId": "<the transform>", "inputs": '
        "[<the source subtree>]} with the organism the message names, and no "
        "transform back."
    )
