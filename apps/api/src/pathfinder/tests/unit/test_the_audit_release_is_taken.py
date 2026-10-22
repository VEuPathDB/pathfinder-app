"""The tool server release this application takes publishes the audit names the job reads."""

from __future__ import annotations

import veupathdb_mcp.audit
import veupathdb_mcp.tools

_AUDIT_NAMES = {
    "FusionVerdict",
    "GeneEvidence",
    "GeneFusionAudit",
    "GeneLengthAudit",
    "GeneRow",
    "GeneticCode",
    "GenomePriorities",
    "GenomePriority",
    "GenomePseudogeneCalls",
    "MissingGeneAudit",
    "MissingVerdict",
    "OrganelleGeneAudit",
    "OrganelleVerdict",
    "PseudogeneCall",
    "PseudogeneCallAudit",
    "RateBounds",
    "SPLIT_MAX_GAP",
    "SelenoproteinEndAudit",
    "SideVerdict",
    "StrainModelAudit",
    "call_length",
    "classify",
    "gene_rows",
    "genes_of_genome",
    "genome_priorities",
    "orthologs_of",
    "pseudogene_calls_of",
    "rate_with_bounds",
    "relatives_median",
    "tie_break",
}
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
}


def test_the_audit_package_publishes_what_the_job_reads() -> None:
    assert sorted(_AUDIT_NAMES - set(veupathdb_mcp.audit.__all__)) == []


def test_the_tools_package_publishes_the_checks() -> None:
    assert sorted(_TOOL_NAMES - set(veupathdb_mcp.tools.__all__)) == []
