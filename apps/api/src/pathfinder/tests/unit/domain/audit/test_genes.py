from __future__ import annotations

import pytest
from veupathdb_mcp.audit import GeneId

from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.domain.audit.genes import evidence_genes, named_genes
from pathfinder.domain.audit.scope import GenePairTarget, SingleGeneTarget
from pathfinder.tests._support.audit import NF54_PIGA, PIGA, PIGA_INTACT
from pathfinder.tests._support.audit_evidence import K13, PIGA_EVIDENCE, evidence_of

ALIAS = "PF10_0115"


def test_a_target_names_its_genes_as_the_site_resolved_them() -> None:
    stored = PseudogeneConfirmation(
        result=PIGA_INTACT.model_copy(
            update={
                "gene_ids": [
                    GeneId(given=NF54_PIGA, resolved=NF54_PIGA),
                    GeneId(given=ALIAS, resolved=PIGA),
                ]
            }
        )
    )
    aliased = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, ALIAS))
    assert named_genes(aliased, None) == (NF54_PIGA, ALIAS)
    assert named_genes(aliased, stored) == (NF54_PIGA, PIGA)
    assert named_genes(
        SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",)), None
    ) == ("NF54_SHORT",)


def test_two_genes_the_site_resolved_to_one_are_named_once() -> None:
    stored = PseudogeneConfirmation(
        result=PIGA_INTACT.model_copy(
            update={
                "strain_gene": PIGA,
                "gene_ids": [
                    GeneId(given=ALIAS, resolved=PIGA),
                    GeneId(given=PIGA, resolved=PIGA),
                ],
            }
        )
    )
    aliased = GenePairTarget(check="pseudogene_call", genes=(ALIAS, PIGA))
    assert named_genes(aliased, stored) == (PIGA,)


def test_a_confirmation_that_does_not_name_a_target_gene_is_refused() -> None:
    stored = PseudogeneConfirmation(result=PIGA_INTACT)
    aliased = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, ALIAS))
    with pytest.raises(KeyError, match=ALIAS):
        named_genes(aliased, stored)


def test_evidence_names_the_reference_and_the_genes_it_read_once_each() -> None:
    payloads: list[EvidencePayload] = [
        ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=PIGA_INTACT)),
        RelativesEvidence(
            reference_gene=K13,
            reference_length=461,
            model_length=461,
            relatives_median=461.0,
            relative_lengths={},
            relatives_tier=None,
            side=None,
            reference_organism=None,
        ),
        GeneEvidencePayload(
            genes=(PIGA, K13), evidence=(PIGA_EVIDENCE, evidence_of(K13))
        ),
    ]
    assert evidence_genes(payloads) == (K13, PIGA)
    assert evidence_genes(payloads[:1]) == ()
