"""The library answer each audit check stores as its confirmation."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator
from veupathdb_mcp.audit import (
    FusionVerdict,
    GeneFusionAudit,
    GeneLengthAudit,
    IntronAudit,
    IntronVerdict,
    LengthClass,
    LengthVerdict,
    MissingGeneAudit,
    MissingVerdict,
    OrganelleGeneAudit,
    OrganelleVerdict,
    PseudogeneCallAudit,
    PseudogeneVerdict,
    SecVerdict,
    SelenoproteinEndAudit,
    SideVerdict,
    StrainModelAudit,
)

type FindingVerdict = (
    PseudogeneVerdict
    | SecVerdict
    | LengthVerdict
    | LengthClass
    | FusionVerdict
    | SideVerdict
    | MissingVerdict
    | OrganelleVerdict
    | IntronVerdict
)


class PseudogeneConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["pseudogene_call"] = "pseudogene_call"
    result: PseudogeneCallAudit

    @property
    def verdict(self) -> PseudogeneVerdict:
        return self.result.verdict


class SelenoproteinConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["selenoprotein_end"] = "selenoprotein_end"
    result: SelenoproteinEndAudit

    @property
    def verdict(self) -> SecVerdict:
        return self.result.verdict


class LengthConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["gene_length", "gene_split"]
    result: GeneLengthAudit

    @model_validator(mode="after")
    def _genes_of_check(self) -> Self:
        expected = 1 if self.check == "gene_length" else 2
        if len(self.result.genes) != expected:
            msg = f"{self.check} reads {expected} genes, not {len(self.result.genes)}"
            raise ValueError(msg)
        return self

    @property
    def verdict(self) -> LengthVerdict:
        return self.result.verdict


class FusionConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["gene_fusion"] = "gene_fusion"
    result: GeneFusionAudit

    @property
    def verdict(self) -> LengthClass | FusionVerdict:
        fusion = self.result.fusion
        return self.result.length_class if fusion is None else fusion.verdict


class StrainConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["strain_model"] = "strain_model"
    result: StrainModelAudit

    @property
    def verdict(self) -> SideVerdict:
        return self.result.side


class MissingGeneConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["missing_gene"] = "missing_gene"
    result: MissingGeneAudit

    @property
    def verdict(self) -> MissingVerdict:
        return self.result.verdict


class OrganelleConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["organelle_join"] = "organelle_join"
    result: OrganelleGeneAudit

    @property
    def verdict(self) -> OrganelleVerdict:
        return self.result.verdict


class IntronConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["intron_support"] = "intron_support"
    result: IntronAudit

    @property
    def verdict(self) -> IntronVerdict:
        return self.result.verdict


Confirmation = Annotated[
    PseudogeneConfirmation
    | SelenoproteinConfirmation
    | LengthConfirmation
    | FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation
    | IntronConfirmation,
    Field(discriminator="check"),
]
