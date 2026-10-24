"""Fusion, strain, missing-gene, organelle and intron answers from the library's recorded cases."""

from __future__ import annotations

from pathlib import Path

from veupathdb_mcp.audit import (
    FusionVerdict,
    GeneFusionAudit,
    GeneticCode,
    IntronAudit,
    LengthCheck,
    MissingGeneAudit,
    MissingVerdict,
    NotRead,
    OrganelleGeneAudit,
    OrganelleVerdict,
    SideVerdict,
    StrainModelAudit,
)

from pathfinder.tests._support.audit import (
    NF54,
    P3D7,
    relative_organisms,
    resolved_ids,
)

FRAGILE_RPT6 = "AK88_02763"
COATNEYI_RPT6 = "PCOAH_00051830"
PCYM_PKAC = "PcyM_0736700"
PCYB_PKAC = "PCYB_074210"
ARI_NAC = "TGARI_257090"
GT1 = "Toxoplasma gondii GT1"
CYTB = "PF3D7_MIT02300"
NF54_MITO = "CM019798.1"
_UNPARTNERED = {"partner_group": None, "partner_product": None, "partner_copies": None}
_FUSIONS: dict[str, dict[str, object]] = {
    "EXTRA_MATCHES_NEIGHBOUR": {
        "partner": "PCOAH_00051820",
        "closest_neighbour": None,
        "neighbour_windows": 56,
        "partner_group": "OG8_0090231",
        "partner_product": "Uncharacterized protein",
        "partner_copies": [],
    },
    "EXTRA_UNEXPLAINED": {
        "partner": None,
        "closest_neighbour": "PCOAH_00051820",
        "neighbour_windows": 2,
        **_UNPARTNERED,
    },
    "NO_EXTRA": {
        "extra": [],
        "partner": None,
        "closest_neighbour": None,
        "neighbour_windows": 0,
        **_UNPARTNERED,
    },
}


def _fused(length_class: str, ratio: float, fusion: object) -> GeneFusionAudit:
    return GeneFusionAudit.model_validate(
        {
            "gene_ids": resolved_ids(FRAGILE_RPT6),
            "genes": [FRAGILE_RPT6],
            "length_class": length_class,
            "ratio": ratio,
            "group_median": 424.0,
            "group_copies": 1.0,
            "group_spread": 0.0,
            "organisms": 63,
            "reference_gene": COATNEYI_RPT6,
            "fusion": fusion,
        }
    )


def fusion(verdict: FusionVerdict) -> GeneFusionAudit:
    neighbours = [f"PCOAH_000518{n}0" for n in (0, 1, 2, 4, 5, 6)]
    checked = {
        "extra": [(1, 220), (221, 270), (271, 690)],
        "neighbours": neighbours,
        "product": "26S protease regulatory subunit 8",
        **_FUSIONS[verdict],
    }
    return _fused("LONG", 2.583, checked)


def not_long(length_class: str, ratio: float) -> GeneFusionAudit:
    return _fused(length_class, ratio, None)


_RELATIVE_LENGTHS: dict[str, tuple[int, ...]] = {
    "STRAIN_SHORT": (335, 345),
    "REFERENCE_LONG": (275, 285),
    "UNCLEAR": (500, 520),
    "NO_RELATIVES": (),
    "NOT_JUDGED": (),
}
_ENCODED = {
    "verdict": "GENOME_ENCODES",
    "counts": {"model": 27, "genome_same_strand": 5, "weak": 1},
    "track": "MMMMGGGGGw" + "M" * 23,
}
_ABSENT = {
    "verdict": "ABSENT",
    "counts": {"model": 27, "absent": 6},
    "track": "MMMM" + "." * 6 + "M" * 23,
}


def _strain_relatives(side: SideVerdict) -> dict[str, object]:
    members = [
        {"organism": organism, "length": length}
        for organism, length in zip(
            relative_organisms(2), _RELATIVE_LENGTHS[side], strict=False
        )
    ]
    return {
        "tier": "SAME_GENUS" if members else None,
        "members": members,
        "missing": None if members else "PARALOGS",
        "copies_per_organism": 1.0 if members else 8.0,
    }


_PKAC_PAIR = {
    "extra": [],
    "gene_ids": resolved_ids(PCYM_PKAC, PCYB_PKAC),
    "strain_gene": PCYM_PKAC,
    "reference_gene": PCYB_PKAC,
    "strain_length": 280,
    "reference_length": 341,
}


def strain(side: SideVerdict) -> StrainModelAudit:
    read = _ABSENT if side == "NOT_JUDGED" else _ENCODED
    return StrainModelAudit.model_validate(
        {
            **_PKAC_PAIR,
            "lost": [(41, 100)],
            "dna": {**read, "windows": 33, "ns_in_window": 0, "at_contig_edge": False},
            "not_read": None,
            "nearby_paralogs": [],
            "side": side,
            "relatives": _strain_relatives(side),
            "code": GeneticCode.STANDARD,
            "code_inferred": True,
        }
    )


_RESIDUAL: dict[str, object] = {
    "tier": None,
    "members": [],
    "missing": "RESIDUAL_GROUP",
    "copies_per_organism": None,
}


def unread_strain(reason: NotRead) -> StrainModelAudit:
    return StrainModelAudit.model_validate(
        {
            **_PKAC_PAIR,
            "lost": [] if reason == "NO_LOST_RUN" else [(41, 100)],
            "dna": LengthCheck.not_checked(),
            "not_read": reason,
            "nearby_paralogs": (
                ["PcyM_0736800"] if reason == "PARALOG_IN_WINDOW" else []
            ),
            "side": "NOT_JUDGED",
            "relatives": (
                _RESIDUAL
                if reason == "UNQUALIFIED"
                else _strain_relatives("NO_RELATIVES")
            ),
            "code": None,
            "code_inferred": False,
        }
    )


_NAC_ANCHORS = {
    "left": {
        "neighbour": "TGARI_257070",
        "gene": "TGGT1_257070",
        "sequence_id": "TGGT1_chrVIIb",
        "start": 4176004,
        "end": 4180213,
        "strand": "-",
    },
    "right": {
        "neighbour": "TGARI_257100",
        "gene": "TGGT1_257100",
        "sequence_id": "TGGT1_chrVIIb",
        "start": 4153116,
        "end": 4154810,
        "strand": "+",
    },
}
_FOUND = {"windows": 34, "found": 34, "span": (4156680, 4157729), "ns": 0}
_EMPTY = {"windows": 34, "found": 0, "span": None, "ns": 0}
_PSEUDOGENE_OVER_SPAN = {
    "gene": "TGGT1_257091",
    "product": "conserved protein",
    "ortholog_group": "OG8_0000001",
    "protein_length": None,
    "start": 4156580,
    "end": 4157479,
    "strand": "+",
    "pseudo": True,
    "gene_type": "pseudogene",
}
_SCANS: dict[str, dict[str, object]] = {
    "IN_DNA_UNANNOTATED": {"located": _FOUND},
    "IN_DNA_OTHER_MODEL": {"located": _FOUND, "overlapping": [_PSEUDOGENE_OVER_SPAN]},
    "PARTIAL": {
        "located": {**_FOUND, "found": 14, "span": (4156680, 4157129)},
        "open_frame": {"length": 150, "identical": 140},
        "intact_frame": True,
    },
    "GAP": {"located": {**_EMPTY, "ns": 2400}},
    "NOT_IN_DNA": {"located": _EMPTY},
}
_NOT_READ: dict[str, object] = {
    "anchors": None,
    "located": None,
    "overlapping": None,
    "open_frame": None,
    "stops": None,
    "intact_frame": None,
    "code": None,
    "code_inferred": False,
}


def _scanned(verdict: MissingVerdict) -> dict[str, object]:
    if verdict in {"NO_SYNTENY", "ANNOTATED_IN_GENOME"}:
        return _NOT_READ
    found = verdict in {"IN_DNA_UNANNOTATED", "IN_DNA_OTHER_MODEL"}
    return {
        "anchors": _NAC_ANCHORS,
        "overlapping": [],
        "open_frame": {"length": 196, "identical": 196} if found else None,
        "stops": [163] if found else [],
        "intact_frame": False if found else None,
        "code": GeneticCode.STANDARD,
        "code_inferred": True,
        **_SCANS[verdict],
    }


def missing(verdict: MissingVerdict) -> MissingGeneAudit:
    annotated = verdict == "ANNOTATED_IN_GENOME"
    members = [{"gene": "TGGT1_999999", "sequence_id": "TGGT1_chrX", "start": 100000}]
    return MissingGeneAudit.model_validate(
        {
            "verdict": verdict,
            "gene_ids": resolved_ids(ARI_NAC),
            "example_gene": ARI_NAC,
            "absent_organism": GT1,
            "example_length": 359,
            "annotated_members": members if annotated else [],
            **_scanned(verdict),
        }
    )


_CONTIGS: dict[str, tuple[str, str, int, int, int, int]] = {
    "SPLIT_AT_JOIN": (NF54, NF54_MITO, 6054, 274, 376, 87),
    "INTACT_ON_THE_LINE": (P3D7, "Pf3D7_MIT_v3", 5967, 376, 376, 0),
    "NOT_FOUND": ("Plasmodium falciparum SN01", "PfSN01_MT", 6093, 291, 291, 127),
}


def organelle(verdict: OrganelleVerdict) -> OrganelleGeneAudit:
    organism, contig, length, linear, circular, overlap = _CONTIGS[verdict]
    return OrganelleGeneAudit(
        verdict=verdict,
        best_linear=linear,
        best_circular=circular,
        reference_length=376,
        overlap_bases=overlap,
        overlap_mismatches=0,
        gene_ids=resolved_ids(CYTB),
        organism=organism,
        sequence_id=contig,
        reference_gene=CYTB,
        contig_length=length,
        code=GeneticCode.STANDARD,
        code_inferred=True,
    )


_MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "audit_models"


def _recorded_introns(name: str) -> IntronAudit:
    return IntronAudit.model_validate_json((_MODELS / name).read_text())


PKAC_INTRONS = _recorded_introns("pkac_introns.json")
AFU8_INTRONS = _recorded_introns("afu8_introns.json")
AGAP7279_INTRONS = _recorded_introns("agap7279_introns.json")
AGAP3685_INTRONS = _recorded_introns("agap3685_introns.json")
