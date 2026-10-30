from __future__ import annotations

from uuid import UUID

from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.facts import audit_finding_fact
from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.domain.read_facts import read_fact
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.services.audit.finding_views import (
    EvidenceView,
    FindingDetail,
    FindingView,
)

_RUN = UUID("0b6f3a52-6a1e-4c55-9a62-1f1d2a3b4c5d")
_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"
_GENOME = "Examplea alpha A"
_LENGTH = "evidence.0.payload.confirmation.result.strainCdsLength"


def _intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=897,
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


def _fact() -> StatisticFact:
    return audit_finding_fact(
        _RUN,
        FindingDetail(
            site_id="plasmodb",
            finding=FindingView(
                id=29,
                genome=_GENOME,
                screened_genome=_GENOME,
                paired_genome=None,
                target=GenePairTarget(
                    check="pseudogene_call", genes=(_STRAIN, _REFERENCE)
                ),
                sampled=True,
                status="confirmed",
                error_type="intact_gene_called_pseudogene",
                certainty="high",
                judged=True,
                impact=None,
                weighing=None,
                requests=4,
                attempts=1,
                stopped=0,
                message=None,
                reviewed=False,
                verdict="INTACT",
                from_target=True,
                review_line=None,
                genes=[],
            ),
            evidence=[
                EvidenceView(
                    kind="confirmation",
                    status="stored",
                    payload=ConfirmationEvidence(
                        confirmation=PseudogeneConfirmation(result=_intact())
                    ),
                    requests=4,
                    attempts=1,
                    stopped=0,
                    message=None,
                )
            ],
            facts=[],
            review=None,
            review_text=None,
            genes=[],
            models=None,
        ),
    )


def test_a_finding_fact_names_each_value_by_its_path_in_the_answer() -> None:
    fact = _fact()

    assert (fact.value(_LENGTH), fact.value("evidence.0.kind")) == (
        "897",
        "confirmation",
    )
    assert fact.value("confirmation.confirmation.result.strainCdsLength") is None


def test_the_facts_show_the_findings_id_and_certainty_and_not_its_payload() -> None:
    shown = {row.label: row.value for row in read_fact(_fact()).rows}

    assert (shown["finding id"], shown["finding certainty"]) == ("29", "high")
    assert [label for label in shown if "cds length" in label] == []
