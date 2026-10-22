"""Gene evidence read from the recorded PIGA, K13, GLO1 and DMAW gene records and their sites' gene record types."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict
from veupathdb.wdk import WDKRecordInstance
from veupathdb_mcp.audit import GeneEvidence, GeneId

from pathfinder.tests._support.audit import PIGA

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audit_evidence"
K13 = "PF3D7_1343700"
GLO1 = "LmjF.35.3010"
DMAW = "Afu2g18040"
_RECORDED = {
    PIGA: ("evidence_pfal3D7_piga.json", "plasmodb"),
    K13: ("evidence_pfal3D7_k13.json", "plasmodb"),
    GLO1: ("evidence_lmajFriedlin_glo1.json", "tritrypdb"),
    DMAW: ("evidence_afumAf293_dmaw.json", "fungidb"),
}


class _Table(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str


class _RecordType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    tables: list[_Table]


def _body(name: str) -> str:
    return (FIXTURES / name).read_text()


def declared(site: str) -> list[str]:
    served = _RecordType.model_validate_json(_body(f"evidence_{site}_tables.json"))
    return [table.name for table in served.tables]


def recorded_evidence(gene: str) -> GeneEvidence:
    name, site = _RECORDED[gene]
    record = WDKRecordInstance.model_validate_json(_body(name))
    named = GeneId(given=gene, resolved=gene)
    return GeneEvidence.from_record(named, record, declared(site))


K13_EVIDENCE = recorded_evidence(K13)
PIGA_EVIDENCE = recorded_evidence(PIGA)
UNCITED_EVIDENCE = PIGA_EVIDENCE.model_copy(update={"pubmed": 0})


def evidence_of(gene: str) -> GeneEvidence:
    if gene in _RECORDED:
        return recorded_evidence(gene)
    return PIGA_EVIDENCE.model_copy(
        update={"gene": gene, "gene_ids": [GeneId(given=gene, resolved=gene)]}
    )
