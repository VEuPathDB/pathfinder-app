"""The tool server release this application takes publishes the audit names the job reads."""

from __future__ import annotations

from importlib.metadata import version
from typing import get_args

import veupathdb_mcp
import veupathdb_mcp.audit
import veupathdb_mcp.catalog
import veupathdb_mcp.gene_lookup
import veupathdb_mcp.tools
from veupathdb_mcp.audit import IntronVerdict

_AUDIT_NAMES = {
    "COVERAGE_HEADERS_READ",
    "FusionVerdict",
    "GeneEvidence",
    "GeneFusionAudit",
    "GeneLengthAudit",
    "GeneRow",
    "GeneIdProblem",
    "GeneIdRefusal",
    "GeneListDataset",
    "GeneticCode",
    "GroupMember",
    "GenomePriorities",
    "GenomePriority",
    "GenomePseudogeneCalls",
    "INTRON_STORE_READS",
    "MAX_LIST_IDS",
    "MODEL_READS_PER_FINDING",
    "RECORD_READS_PER_CALL",
    "MissingGeneAudit",
    "MissingVerdict",
    "OrganelleGeneAudit",
    "OrganelleVerdict",
    "OrthologGroup",
    "PseudogeneCall",
    "PseudogeneCallAudit",
    "RateBounds",
    "ReadModels",
    "SPLIT_MAX_GAP",
    "TooManyIdsError",
    "SelenoproteinEndAudit",
    "SideVerdict",
    "StrainModelAudit",
    "call_length",
    "classify",
    "genes_of_genome",
    "genome_priorities",
    "read_gene_list",
    "orthologs_of",
    "pseudogene_calls_of",
    "rate_with_bounds",
    "record_proteins",
    "record_rows",
    "relatives_median",
    "tie_break",
    "upload_gene_list",
}
_GENE_LOOKUP_NAMES = {"GeneIdFound", "read_each_gene_id"}
_CATALOG_NAMES = {"NoGeneRecordsError", "require_gene_records"}
_TOOL_NAMES = {
    "audit_gene_evidence",
    "audit_gene_fusion",
    "audit_gene_length",
    "audit_gene_split",
    "audit_genome_priority",
    "audit_genome_pseudogene_calls",
    "audit_missing_gene",
    "audit_organelle_gene",
    "audit_pseudogene_call",
    "audit_selenoprotein_end",
    "audit_strain_model",
    "build_every_species_expression",
}


def test_the_audit_package_publishes_what_the_job_reads() -> None:
    assert sorted(_AUDIT_NAMES - set(veupathdb_mcp.audit.__all__)) == []


def test_the_lookup_and_catalog_packages_publish_the_gene_id_reads() -> None:
    assert sorted(_GENE_LOOKUP_NAMES - set(veupathdb_mcp.gene_lookup.__all__)) == []
    assert sorted(_CATALOG_NAMES - set(veupathdb_mcp.catalog.__all__)) == []


def test_the_tools_package_publishes_the_checks() -> None:
    assert sorted(_TOOL_NAMES - set(veupathdb_mcp.tools.__all__)) == []


def test_the_intron_check_names_its_three_new_verdicts() -> None:
    new = {"UNSUPPORTED_REPLACED", "UNSUPPORTED_NONCANONICAL", "UNSUPPORTED_RETAINED"}
    assert sorted(new - set(get_args(IntronVerdict.__value__))) == []


def test_the_pinned_releases_are_installed() -> None:
    assert (
        version("veupathdb-mcp"),
        veupathdb_mcp.__version__,
        version("veupathdb-py"),
        version("assistant-core"),
    ) == ("0.2.0b39", "0.2.0b39", "0.1.0b22", "0.3.0b10")
