"""A synthetic site for the planner tests: its organisms, organism report, BUSCO gaps, gene organisms, proteins and junction tracks."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pytest
from veupathdb.jbrowse import TrackConfig
from veupathdb.wdk import WDKAnswer
from veupathdb_mcp.audit import BuscoScore, GenomePriority

from pathfinder.domain.audit.planning import PlanRequest
from pathfinder.domain.audit.scope import GenePairTarget, GeneTarget, SingleGeneTarget
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import planning

SITE = "plasmodb"
SITE_NAME = "PlasmoDB"
STRAINS = tuple(f"Examplea alpha {letter}" for letter in "ABCDEFGHI")
ALPHA_R = "Examplea alpha R"
BETA_R = "Examplea beta R"
BETA_S = "Examplea beta S"
OUTGROUP = "Otherus gamma G"
ORGANISMS = sorted((*STRAINS, ALPHA_R, BETA_R, BETA_S, OUTGROUP))
GAPS = {name: float(k + 1) for k, name in enumerate(STRAINS)}
ABBREVS = {"EXA": "exaA", "EXB": "exaB"}
PROTEINS = {"EXR_0002": "MKUA", "EXR_0012": "MKLA"}
RNA_KEPT = SingleGeneTarget(check="intron_support", genes=("EXA_0007",))
RNA_REFUSED = SingleGeneTarget(check="intron_support", genes=("EXB_0001",))
SEC_KEPT = GenePairTarget(check="selenoprotein_end", genes=("EXA_0002", "EXR_0002"))
SEC_REFUSED = GenePairTarget(check="selenoprotein_end", genes=("EXA_0012", "EXR_0012"))
SEC_UNSERVED = GenePairTarget(check="selenoprotein_end", genes=("EXA_0022", "EXR_0022"))


def _record(organism: str) -> dict[str, object]:
    reference = "yes" if organism in {ALPHA_R, BETA_R} else "no"
    served = {"is_reference_strain": reference} if organism != BETA_S else {}
    return {
        "displayName": organism,
        "id": [{"name": "source_id", "value": f"TAXON_{organism}"}],
        "attributes": {
            "source_id": f"TAXON_{organism}",
            "organism_full": organism,
            "genome_source": "Example",
            "genome_version": "1",
            "annotation_source": "Example",
            "annotation_version": "1",
            "database_version": "2026-01-01",
            "build_introduced": "1",
            "build_latest_update": "2",
            "ncbi_tax_id": "1",
            **served,
        },
        "tables": {},
    }


def _priority(organism: str, gap: float) -> GenomePriority:
    def score(complete: float) -> BuscoScore:
        return BuscoScore(
            complete=complete, fragmented=0.0, missing=100 - complete, total=100
        )

    return GenomePriority(
        organism=organism, protein=score(90.0 - gap), genome=score(90.0), lineage="x"
    )


class FakeJBrowse:
    def __init__(self, site: FakeSite) -> None:
        self.site = site

    async def junction_tracks(self, abbrev: str) -> list[TrackConfig]:
        self.site.calls.append("junction_tracks")
        if abbrev == "exaA":
            return [TrackConfig(label="junctions", store_class="JBrowse/Store/Tabix")]
        return []


class FakeSite:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.organisms = list(ORGANISMS)

    async def list_organisms(self, site_id: str) -> list[str]:
        assert site_id == SITE
        self.calls.append("list_organisms")
        return sorted(self.organisms)

    async def organism_report(
        self, site_id: str, attributes: Sequence[str]
    ) -> WDKAnswer:
        del site_id, attributes
        self.calls.append("organism_report")
        records = [_record(name) for name in self.organisms if name != OUTGROUP]
        return WDKAnswer.model_validate(
            {"records": records, "meta": {"totalCount": len(records)}}
        )

    async def genome_priorities(self, site_id: str) -> list[GenomePriority]:
        del site_id
        self.calls.append("genome_priorities")
        return [_priority(name, gap) for name, gap in GAPS.items()]

    async def gene_organism(self, site_id: str, gene: str) -> str:
        del site_id
        self.calls.append("gene_organism")
        return ABBREVS[gene[:3]]

    async def record_proteins(
        self, site_id: str, gene_ids: list[str]
    ) -> dict[str, str]:
        del site_id
        self.calls.append("record_proteins")
        return {gene: PROTEINS[gene] for gene in gene_ids if gene in PROTEINS}

    def jbrowse(self, site_id: str) -> FakeJBrowse:
        assert site_id == SITE
        return FakeJBrowse(self)


def faked_site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    fake = FakeSite()
    monkeypatch.setattr(planning, "list_organisms", fake.list_organisms)
    monkeypatch.setattr(planning, "organism_report", fake.organism_report)
    monkeypatch.setattr(planning, "genome_priorities", fake.genome_priorities)
    monkeypatch.setattr(planning, "gene_organism", fake.gene_organism)
    monkeypatch.setattr(planning, "record_proteins", fake.record_proteins)
    monkeypatch.setattr(planning, "get_jbrowse_client", fake.jbrowse)
    return fake


@contextmanager
def setting(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> Iterator[None]:
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv(name)
    get_settings.cache_clear()


def plan_request(*genomes: str, targets: tuple[GeneTarget, ...] = ()) -> PlanRequest:
    return PlanRequest(site_id=SITE, genomes=genomes, targets=targets)
