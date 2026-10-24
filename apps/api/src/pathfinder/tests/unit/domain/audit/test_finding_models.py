"""A finding's gene models, as its stored check result holds them, in genome coordinates."""

from __future__ import annotations

import pytest
from veupathdb_mcp.audit import GeneLengthAudit, GeneSpan, ModelSpans

from pathfinder.domain.audit.confirmations import (
    Confirmation,
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.models import (
    FindingModels,
    KeptIntron,
    ProposedModel,
    StopCodon,
    finding_models,
    stop_codon,
)
from pathfinder.tests._support.audit import PIGA, PIGA_INTACT, short_audit
from pathfinder.tests._support.audit_answers import (
    AFU8_INTRONS,
    AGAP3685_INTRONS,
    AGAP7279_INTRONS,
    DMAW_INTRONS,
    GT1_SELK,
    PKAC_INTRONS,
    PKAC_STRAIN_MODELS,
    RPT6_FUSION,
    missing,
    organelle,
    strain,
)

PCYM, PCYB = (model for model in PKAC_STRAIN_MODELS if model is not None)
RETAINED_TRACK = "E-MTAB-2880:E_20h_F (unique reverse)"


def _proposed(result: object) -> ProposedModel:
    models = finding_models(IntronConfirmation.model_validate({"result": result}))
    assert models is not None
    assert models.proposed is not None
    return models.proposed


def test_an_intron_finding_holds_the_annotated_and_the_proposed_model() -> None:
    models = finding_models(IntronConfirmation(result=PKAC_INTRONS))

    assert models is not None
    assert (models.kind, models.merged, models.stop) == ("intron", None, None)
    assert models.annotated == (PCYM,)
    assert models.proposed == ProposedModel(
        kind="corrected",
        gene="PcyM_0736700",
        exons=(
            (1381622, 1381745),
            (1381887, 1382044),
            (1382281, 1382465),
            (1382631, 1382790),
            (1383064, 1383462),
        ),
        cds=(
            (1381622, 1381745),
            (1381887, 1382044),
            (1382281, 1382465),
            (1382631, 1382790),
            (1383064, 1383462),
        ),
        removed_introns=((1381746, 1382305),),
        junctions=((1381746, 1381886), (1382045, 1382280)),
        junction_reads=(1436, 1686),
        frame_kept=True,
    )


def test_a_shifted_and_a_replaced_intron_propose_the_junction_they_were_read_by() -> (
    None
):
    shifted, replaced = _proposed(DMAW_INTRONS), _proposed(AFU8_INTRONS)

    assert (shifted.gene, shifted.cds, shifted.frame_kept) == (
        "Afu2g18040",
        ((4793606, 4793712), (4793787, 4793908), (4793970, 4795120)),
        True,
    )
    assert (shifted.removed_introns, shifted.junctions, shifted.junction_reads) == (
        ((4793693, 4793790),),
        ((4793713, 4793786),),
        (1226,),
    )
    assert (replaced.cds, replaced.exons, replaced.frame_kept) == (
        ((202062, 202208), (202267, 202401)),
        ((202062, 202208), (202267, 202401)),
        False,
    )
    assert (replaced.removed_introns, replaced.junctions, replaced.junction_reads) == (
        ((202070, 202266),),
        ((202209, 202266),),
        (18608,),
    )
    assert (shifted.kind, replaced.kind, shifted.kept, replaced.kept) == (
        "corrected",
        "corrected",
        (),
        (),
    )


def test_a_retained_intron_is_kept_as_exon_in_the_corrected_model() -> None:
    proposed = _proposed(AGAP3685_INTRONS)

    assert proposed.kept == (
        KeptIntron(
            start=41952076,
            end=41952160,
            outcome="RETAINED",
            motif="GT..AG",
            depth_share=0.533,
            covered_share=0.988,
            track=RETAINED_TRACK,
        ),
    )
    assert proposed.exons == (
        (41952051, 41952902),
        (41953562, 41953639),
        (41953733, 41953990),
        (41954090, 41954101),
    )
    assert (proposed.kind, proposed.cds[0], proposed.removed_introns) == (
        "corrected",
        (41952051, 41952902),
        ((41952076, 41952160),),
    )
    assert (proposed.junctions, proposed.junction_reads, proposed.frame_kept) == (
        (),
        (),
        False,
    )


def test_a_retained_intron_with_no_correction_read_proposes_the_exon_alone() -> None:
    unread = AGAP3685_INTRONS.model_copy(
        update={
            "corrected_cds": None,
            "corrected_protein": None,
            "frame_kept": None,
            "code": None,
            "code_inferred": False,
            "orthologs": None,
            "correction_reason": "the correction was not read",
        }
    )

    proposed = _proposed(unread)

    assert (proposed.kind, proposed.cds, proposed.frame_kept) == ("retained", (), None)
    assert proposed.exons == (
        (41950997, 41952902),
        (41953562, 41953639),
        (41953733, 41953990),
        (41954090, 41954101),
    )
    assert proposed.removed_introns == ((41952076, 41952160),)
    assert [k.outcome for k in proposed.kept] == ["RETAINED"]


def test_an_unexplained_intron_proposes_no_model() -> None:
    models = finding_models(IntronConfirmation(result=AGAP7279_INTRONS))

    assert models is not None
    assert (models.kind, models.proposed) == ("intron", None)
    assert (models.annotated[0].gene, models.annotated[0].seqid) == (
        "AGAP007279",
        "AgamP4_2L",
    )


def test_a_strain_finding_holds_the_strain_model_beside_its_reference() -> None:
    models = finding_models(StrainConfirmation(result=strain("STRAIN_SHORT")))

    assert models == FindingModels(kind="strain", annotated=(PCYM, PCYB))
    assert [(m.gene, m.seqid, m.strand) for m in (PCYM, PCYB)] == [
        ("PcyM_0736700", "PcyM_07", "+"),
        ("PCYB_074210", "DF157099", "+"),
    ]


def test_a_model_the_check_did_not_read_is_left_out() -> None:
    result = strain("STRAIN_SHORT").model_copy(
        update={"models": [None, PCYB], "evidence_unread": ["no CDS row"]}
    )

    assert finding_models(StrainConfirmation(result=result)) == FindingModels(
        kind="strain", annotated=(PCYB,)
    )


def test_a_merge_holds_the_two_genes_beside_the_merged_span() -> None:
    models = finding_models(FusionConfirmation(result=RPT6_FUSION))

    assert models is not None
    assert models.kind == "merge"
    assert models.merged == GeneSpan(
        gene="AK88_02763", seqid="KQ001672", strand="+", start=202826, end=207689
    )
    assert [(m.gene, m.seqid, m.cds) for m in models.annotated] == [
        ("PCOAH_00051830", "CP016252", [(251514, 252788)]),
        ("PCOAH_00051820", "CP016252", [(248191, 250131)]),
    ]


def test_a_selenoprotein_end_marks_its_stop_codon() -> None:
    models = finding_models(SelenoproteinConfirmation(result=GT1_SELK))

    assert models is not None
    assert (models.kind, [m.gene for m in models.annotated]) == (
        "sec_end",
        ["TGGT1_316600", "TGME49_316600"],
    )
    assert models.stop == StopCodon(
        gene="TGGT1_316600", seqid="TGGT1_chrXI", start=5361334, end=5361336
    )


def test_a_stop_codon_on_the_minus_strand_is_the_first_coding_base() -> None:
    minus = ModelSpans(
        gene="EXA_1",
        transcript="EXA_1.1",
        seqid="EXA_01",
        strand="-",
        exons=[(90, 400), (500, 700)],
        cds=[(100, 400), (500, 650)],
    )

    assert stop_codon(minus) == StopCodon(
        gene="EXA_1", seqid="EXA_01", start=100, end=102
    )


def test_a_length_finding_holds_the_models_of_its_genes() -> None:
    short = short_audit("PcyM_0736700", reference_gene="PCYB_074210")
    read = GeneLengthAudit.model_validate({**dict(short), "models": [PCYM]})

    models = finding_models(LengthConfirmation(check="gene_length", result=read))
    unread = finding_models(LengthConfirmation(check="gene_length", result=short))

    assert models == FindingModels(kind="length", annotated=(PCYM,))
    assert unread is None


def test_a_pseudogene_finding_holds_the_reference_model() -> None:
    reference = ModelSpans(
        gene=PIGA,
        transcript="PF3D7_1032400.1",
        seqid="Pf3D7_10_v3",
        strand="-",
        exons=[(1303298, 1304315)],
        cds=[(1303298, 1304315)],
    )
    result = PIGA_INTACT.model_copy(update={"reference_model": reference})

    assert finding_models(PseudogeneConfirmation(result=result)) == FindingModels(
        kind="pseudogene", annotated=(reference,)
    )
    assert [finding_models(PseudogeneConfirmation(result=PIGA_INTACT))] == [None]


def test_a_check_that_read_no_model_of_the_gene_it_judged_draws_none() -> None:
    me49 = GT1_SELK.models[1]
    no_gt1 = GT1_SELK.model_copy(
        update={"models": [None, me49], "evidence_unread": ["no CDS row"]}
    )
    confirmations: list[Confirmation] = [
        IntronConfirmation(result=PKAC_INTRONS.model_copy(update={"model": None})),
        StrainConfirmation(result=strain("UNCLEAR", models=[])),
        SelenoproteinConfirmation(result=no_gt1),
        OrganelleConfirmation(result=organelle("SPLIT_AT_JOIN")),
        MissingGeneConfirmation(result=missing("IN_DNA_UNANNOTATED")),
    ]

    assert [finding_models(c) for c in confirmations] == [None] * 5


@pytest.mark.parametrize(
    ("kind", "parts", "reason"),
    [
        ("strain", {"merged": RPT6_FUSION.merged}, "a merged span only for a merge"),
        ("merge", {}, "a merged span only for a merge"),
        ("intron", {"stop": stop_codon(PCYM)}, "a stop codon only for a selenoprotein"),
        ("sec_end", {}, "a stop codon only for a selenoprotein"),
        (
            "length",
            {"proposed": _proposed(PKAC_INTRONS)},
            "a proposed model only for an intron",
        ),
    ],
)
def test_each_kind_holds_only_its_parts(
    kind: str, parts: dict[str, object], reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        FindingModels.model_validate({"kind": kind, "annotated": [PCYM], **parts})
