from __future__ import annotations

import pytest
from veupathdb_mcp.audit import GeneSpan, NotRead

from pathfinder.domain.audit.check_facts import confirmation_facts
from pathfinder.domain.audit.confirmations import (
    Confirmation,
    FusionConfirmation,
    LengthConfirmation,
    StrainConfirmation,
)
from pathfinder.tests._support.audit import (
    not_checked_audit,
    revised,
    short_audit,
    split_audit,
)
from pathfinder.tests._support.audit_answers import fusion, strain, unread_strain
from pathfinder.tests._support.audit_wire import DD2_YIP1, P3D7_YIP1

UNREAD = "the strain region is unreadable"


def _pairs(confirmation: Confirmation) -> list[tuple[str, str]]:
    return [(fact.label, fact.value) for fact in confirmation_facts(confirmation)]


def test_a_length_check_states_its_group_and_the_parts_it_read() -> None:
    short = revised(
        short_audit(DD2_YIP1, reference_gene=P3D7_YIP1),
        models=[None],
        evidence_unread=[UNREAD],
    )
    assert _pairs(LengthConfirmation(check="gene_length", result=short)) == [
        ("Model", "PfDd2_140076300"),
        ("Reference gene", "PF3D7_1472100"),
        ("Ortholog group median", "200 residues over 10 organisms"),
        ("Length against the median", "0.6 times the median length"),
        (
            "Parts of the reference protein",
            "19: 12 in the model, 7 encoded on the same strand outside the model",
        ),
        ("Unknown bases in the region read", "0"),
        ("At a contig end", "No"),
        ("Genetic code", "Standard (inferred)"),
        ("Evidence not read", UNREAD),
    ]


def test_a_split_pair_names_both_models_and_their_parts() -> None:
    pair = split_audit("A_1", "A_2", reference_gene=P3D7_YIP1)
    facts = _pairs(LengthConfirmation(check="gene_split", result=pair))
    assert (facts[0], facts[4]) == (
        ("Models", "A_1 and A_2"),
        (
            "Parts of the reference protein",
            (
                "19: 9 in the first model, 1 encoded on the same strand outside the model, "
                "9 in the second model"
            ),
        ),
    )


def test_a_length_check_that_read_no_dna_states_each_part_as_not_read() -> None:
    unread = not_checked_audit(["X_1"], "TYPICAL", reference_gene=P3D7_YIP1)
    assert _pairs(LengthConfirmation(check="gene_length", result=unread))[4:] == [
        ("Parts of the reference protein", "Not read"),
        ("Unknown bases in the region read", "Not read"),
        ("At a contig end", "Not read"),
        ("Genetic code", "Not read"),
    ]


def test_a_merge_states_its_extra_part_and_the_neighbour_it_matches() -> None:
    merged = fusion("EXTRA_MATCHES_NEIGHBOUR")
    spanned = revised(
        merged,
        merged=GeneSpan(
            gene="AK88_02763", seqid="PKNOH_S120130", strand="+", start=1200, end=4400
        ),
        models=[None, None],
        evidence_unread=[UNREAD, UNREAD],
    )
    assert _pairs(FusionConfirmation(result=merged)) == [
        ("Model", "AK88_02763"),
        ("Reference gene", "PCOAH_00051830"),
        ("Ortholog group median", "424 residues over 63 organisms"),
        ("Length against the median", "2.583 times the median length"),
        ("Extra residues", "1 to 220, 221 to 270 and 271 to 690"),
        ("Extra parts that match a neighbour", "56 of 66"),
        ("Partner gene", "PCOAH_00051820"),
        (
            "Neighbours read",
            (
                "PCOAH_00051800, PCOAH_00051810, PCOAH_00051820, PCOAH_00051840, "
                "PCOAH_00051850 and PCOAH_00051860"
            ),
        ),
        ("Product", "26S protease regulatory subunit 8"),
        ("Partner's ortholog group", "OG8_0090231"),
        ("Partner's product", "Uncharacterized protein"),
        ("Partner's copies in the group", "None found"),
    ]
    assert _pairs(FusionConfirmation(result=spanned))[-2:] == [
        ("Merged model", "AK88_02763 on PKNOH_S120130, bases 1,200 to 4,400"),
        ("Evidence not read", f"{UNREAD}; {UNREAD}"),
    ]


def test_a_strain_model_states_the_residues_it_lacks_and_its_relatives() -> None:
    assert _pairs(StrainConfirmation(result=strain("STRAIN_SHORT"))) == [
        ("Strain model PcyM_0736700", "280 residues"),
        ("Reference model PCYB_074210", "341 residues"),
        ("Reference residues the strain model lacks", "41 to 100"),
        ("Strain residues the reference lacks", "None found"),
        (
            "The strain's DNA over the lost part",
            "The genome's DNA encodes the part the model lacks",
        ),
        (
            "Parts of the reference protein",
            (
                "33: 27 in the model, 5 encoded on the same strand outside the model, "
                "1 matched weakly"
            ),
        ),
        ("Unknown bases in the region read", "0"),
        ("At a contig end", "No"),
        (
            "Related genomes",
            (
                "Plasmodium relative0 X (335 residues) and Plasmodium relative1 X "
                "(345 residues)"
            ),
        ),
        ("Related genomes from", "The same genus"),
        ("Median of the related genomes", "340 residues"),
        ("Paralogs near the model", "None found"),
        ("Genetic code", "Standard (inferred)"),
    ]


def test_a_strain_with_no_relatives_states_why() -> None:
    facts = dict(_pairs(StrainConfirmation(result=strain("NO_RELATIVES"))))
    assert (facts["Related genomes"], facts["Related genomes from"]) == (
        "None found: the related genomes do not hold one copy each",
        "Not read",
    )


@pytest.mark.parametrize(
    ("reason", "why", "relatives", "paralogs"),
    [
        (
            "NO_LOST_RUN",
            "The strain protein lacks no run of the reference protein",
            "None found: the related genomes do not hold one copy each",
            "None found",
        ),
        (
            "UNQUALIFIED",
            "The ortholog group is a residual group",
            "None found: the ortholog group is a residual group",
            "None found",
        ),
        (
            "PARALOG_IN_WINDOW",
            "A paralog lies in the region the check reads",
            "None found: the related genomes do not hold one copy each",
            "PcyM_0736800",
        ),
    ],
)
def test_a_strain_genome_not_read_states_its_own_reason(
    reason: NotRead, why: str, relatives: str, paralogs: str
) -> None:
    facts = _pairs(StrainConfirmation(result=unread_strain(reason)))
    named = dict(facts)
    assert facts[4:6] == [
        ("The strain's DNA over the lost part", "Not read"),
        ("Why the genome was not read", why),
    ]
    assert (named["Related genomes"], named["Paralogs near the model"]) == (
        relatives,
        paralogs,
    )
    assert "Parts of the reference protein" not in named
