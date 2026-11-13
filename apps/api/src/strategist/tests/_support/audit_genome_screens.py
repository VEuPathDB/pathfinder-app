"""The PIGA rows of the recorded NF54 and 3D7 gene reports, NF135's recorded BUSCO scores, and a site that serves none."""

from __future__ import annotations

from veupathdb_mcp.audit import BuscoScore, GeneRow, GenomePriority

NF135 = "Plasmodium falciparum NF135.C10"
PIGA_PRODUCT = (
    "phosphatidylinositol N-acetylglucosaminyltransferase subunit A, putative"
)
NF54_PIGA_PSEUDOGENE = "PfNF54_100037200:pseudogene"

NF54_PIGA_ROW = GeneRow(
    gene=NF54_PIGA_PSEUDOGENE,
    organism="Plasmodium falciparum NF54",
    ortholog_group="N/A (orthology not determined for pseudogenes)",
    protein_length=None,
    name="",
    product=PIGA_PRODUCT,
    sequence_id="VBRF01000019.1",
    start=1063699,
    end=1065985,
    strand="-",
    pseudo=True,
    gene_type="pseudogene",
)
P3D7_PIGA_ROW = GeneRow(
    gene="PF3D7_1032400",
    organism="Plasmodium falciparum 3D7",
    ortholog_group="OG8_0001100",
    protein_length=461,
    name="PIGA",
    product=PIGA_PRODUCT,
    sequence_id="Pf3D7_10_v3",
    start=1302298,
    end=1305315,
    strand="-",
    pseudo=False,
    gene_type="protein coding gene",
)
NF135_PRIORITY = GenomePriority(
    organism=NF135,
    protein=BuscoScore(complete=93.0, fragmented=0.1, missing=6.9, total=1378),
    genome=BuscoScore(complete=98.4, fragmented=0.3, missing=1.3, total=1378),
    lineage="aconoidasida_odb12",
)


async def no_busco_scores(site_id: str) -> list[GenomePriority]:
    del site_id
    return []
