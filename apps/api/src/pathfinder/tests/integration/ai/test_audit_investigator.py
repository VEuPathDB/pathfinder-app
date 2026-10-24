from __future__ import annotations

import pytest
from pydantic_ai.usage import RunUsage
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.investigator import investigate
from pathfinder.ai.audit.mock import build_audit_mock
from pathfinder.services.audit import investigation
from pathfinder.services.audit.verdicts import conversation_verdicts
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit import seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"


def _intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=900,
        covered=900,
        premature_stops=[],
        residue_differences=0,
        gene_ids=[
            GeneId(given=_STRAIN, resolved=_STRAIN),
            GeneId(given=_REFERENCE, resolved=_REFERENCE),
        ],
        strain_gene=_STRAIN,
        reference_gene=_REFERENCE,
    )


async def test_an_investigation_stores_its_verdicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        return _intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)
    owner = await seed_thread()
    deps = AuditDeps(
        site_id="plasmodb",
        user_id=owner.user_id,
        conversation_id=owner.conversation_id,
        origin="lead",
    )

    spent = RunUsage()
    found = await investigate(
        "is the pseudogene call on EXA_0001 right; its reference gene is EXR_0001",
        deps=deps,
        model=build_audit_mock(),
        usage=spent,
    )

    (verdict,) = found.verdicts
    (fact,) = found.facts
    assert (verdict.verdict, verdict.error_type, verdict.cites) == (
        "error",
        "intact_gene_called_pseudogene",
        ("audit_pseudogene_call:EXA_0001:EXR_0001",),
    )
    assert fact.kind == "gene_check"
    assert [(r.record_id, r.url) for r in found.records] == [
        (gene, gene_record_url("plasmodb", gene)) for gene in (_STRAIN, _REFERENCE)
    ]
    assert spent.requests == 2
    stored = await conversation_verdicts(owner.conversation_id, owner.user_id)
    assert [(v.origin, v.verdict) for v in stored] == [("lead", verdict)]
