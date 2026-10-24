"""The library check each audit target is confirmed by, called in this process."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from fastmcp.exceptions import ToolError
from pydantic import ConfigDict
from veupathdb_mcp.tools import (
    audit_gene_fusion,
    audit_gene_length,
    audit_gene_split,
    audit_intron_support,
    audit_missing_gene,
    audit_organelle_gene,
    audit_pseudogene_call,
    audit_selenoprotein_end,
    audit_strain_model,
)

from pathfinder.domain.audit.confirmations import (
    Confirmation,
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.scope import (
    GenePairTarget,
    GeneTarget,
    MissingGeneTarget,
    OrganelleTarget,
    SingleGeneTarget,
)
from pathfinder.services.audit.units import UNIT_FAILURES, failure_status


class UnitFailure(CamelModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["failed", "unreached"]
    message: str


class DeclinedCheck(CamelModel):
    model_config = ConfigDict(frozen=True)

    message: str


async def _single(site_id: str, target: SingleGeneTarget) -> Confirmation:
    (gene,) = target.genes
    match target.check:
        case "gene_length":
            return LengthConfirmation(
                check="gene_length", result=await audit_gene_length(site_id, gene)
            )
        case "gene_fusion":
            return FusionConfirmation(result=await audit_gene_fusion(site_id, gene))
        case "intron_support":
            return IntronConfirmation(result=await audit_intron_support(site_id, gene))


async def _pair(site_id: str, target: GenePairTarget) -> Confirmation:
    first, second = target.genes
    match target.check:
        case "pseudogene_call":
            return PseudogeneConfirmation(
                result=await audit_pseudogene_call(site_id, first, second)
            )
        case "selenoprotein_end":
            return SelenoproteinConfirmation(
                result=await audit_selenoprotein_end(site_id, first, second)
            )
        case "gene_split":
            return LengthConfirmation(
                check="gene_split",
                result=await audit_gene_split(site_id, first, second),
            )
        case "strain_model":
            return StrainConfirmation(
                result=await audit_strain_model(site_id, first, second)
            )


async def _confirm(site_id: str, target: GeneTarget) -> Confirmation:
    match target:
        case GenePairTarget():
            return await _pair(site_id, target)
        case SingleGeneTarget():
            return await _single(site_id, target)
        case MissingGeneTarget():
            (example,) = target.genes
            return MissingGeneConfirmation(
                result=await audit_missing_gene(
                    site_id, example, target.absent_organism
                )
            )
        case OrganelleTarget():
            (reference,) = target.genes
            return OrganelleConfirmation(
                result=await audit_organelle_gene(
                    site_id, target.organism, target.sequence_id, reference
                )
            )


async def confirm_target(
    site_id: str, target: GeneTarget
) -> Confirmation | UnitFailure | DeclinedCheck:
    try:
        return await _confirm(site_id, target)
    except UNIT_FAILURES as exc:
        match exc:
            case ToolError(__cause__=None):
                return DeclinedCheck(message=str(exc))
            case _:
                return UnitFailure(status=failure_status(exc), message=str(exc))
