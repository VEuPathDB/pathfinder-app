"""Gene record classification by experiment category membership.

Classifies WDK result records as TP / FP / FN / TN based on
whether their gene ID appears in the experiment's curated gene sets.
Handles WDK transcript ID version suffixes (e.g. "GENE.1" -> "GENE").
"""

from assistant_core.platform.types import JSONObject
from veupathdb.wdk import WDKRecordInstance
from veupathdb_mcp.wdk import extract_pk

from pathfinder.services.experiment.types.core import Classification


def classify_records(
    records: list[WDKRecordInstance],
    tp_ids: set[str],
    fp_ids: set[str],
    fn_ids: set[str],
    tn_ids: set[str],
) -> list[JSONObject]:
    """Add a ``classification`` field to records based on gene ID membership."""
    classified: list[JSONObject] = []
    for rec in records:
        gene_id = extract_pk(rec)
        classification = _classify_gene_id(gene_id, tp_ids, fp_ids, fn_ids, tn_ids)
        classified.append(
            {
                **rec.model_dump(by_alias=True),
                "classification": classification,
            },
        )
    return classified


def _classify_gene_id(
    gene_id: str | None,
    tp_ids: set[str],
    fp_ids: set[str],
    fn_ids: set[str],
    tn_ids: set[str],
) -> Classification | None:
    """Return the classification label for a single gene ID, or ``None``."""
    if not gene_id:
        return None

    # WDK transcript IDs include a version suffix (e.g. ".1").
    # Experiment gene sets store the base gene ID without it.
    candidates = [gene_id]
    dot = gene_id.rfind(".")
    if dot > 0:
        candidates.append(gene_id[:dot])

    for gid in candidates:
        if gid in tp_ids:
            return "TP"
        if gid in fp_ids:
            return "FP"
        if gid in fn_ids:
            return "FN"
        if gid in tn_ids:
            return "TN"

    return None
