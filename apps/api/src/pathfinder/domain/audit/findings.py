"""What a checked candidate becomes: the library's answer, the error it names, its certainty."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Literal, Self
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator
from veupathdb_mcp.audit import (
    FusionVerdict,
    GeneEvidence,
    GeneFusionAudit,
    GeneLengthAudit,
    MissingGeneAudit,
    MissingVerdict,
    OrganelleGeneAudit,
    OrganelleVerdict,
    PseudogeneCallAudit,
    SelenoproteinEndAudit,
    SideVerdict,
    StrainModelAudit,
)

from pathfinder.domain.audit.scope import CheckName
from pathfinder.domain.audit.stages import RunStatus, StageName

FindingStatus = Literal[
    "screened", "unsampled", "trying", "confirmed", "failed", "unreached", "unread"
]
EvidenceStatus = Literal["pending", "trying", "stored", "failed", "unreached", "unread"]
EvidenceKind = Literal["confirmation", "relatives", "gene_evidence"]
Certainty = Literal["high", "medium", "low"]
ModelRole = Literal["strain", "reference"]
ErrorType = Literal[
    "intact_gene_called_pseudogene",
    "sec_read_as_stop",
    "truncated_model",
    "split_model",
    "over_extended_model",
    "fused_model",
    "missing_gene",
    "organelle_split_at_join",
]
MAX_STOPS = 3


class PseudogeneConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["pseudogene_call"] = "pseudogene_call"
    result: PseudogeneCallAudit

    @property
    def verdict(self) -> str:
        return self.result.verdict


class SelenoproteinConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["selenoprotein_end"] = "selenoprotein_end"
    result: SelenoproteinEndAudit

    @property
    def verdict(self) -> str:
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
    def verdict(self) -> str:
        return self.result.verdict


class FusionConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["gene_fusion"] = "gene_fusion"
    result: GeneFusionAudit

    @property
    def verdict(self) -> str:
        fusion = self.result.fusion
        return self.result.length_class if fusion is None else fusion.verdict


class StrainConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["strain_model"] = "strain_model"
    result: StrainModelAudit

    @property
    def verdict(self) -> str:
        return self.result.side


class MissingGeneConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["missing_gene"] = "missing_gene"
    result: MissingGeneAudit

    @property
    def verdict(self) -> str:
        return self.result.verdict


class OrganelleConfirmation(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["organelle_join"] = "organelle_join"
    result: OrganelleGeneAudit

    @property
    def verdict(self) -> str:
        return self.result.verdict


Confirmation = Annotated[
    PseudogeneConfirmation
    | SelenoproteinConfirmation
    | LengthConfirmation
    | FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation,
    Field(discriminator="check"),
]


class Classification(CamelModel):
    model_config = ConfigDict(frozen=True)

    error_type: ErrorType | None = None
    certainty: Certainty | None = None
    message: str | None = None
    model_role: ModelRole | None = None

    @model_validator(mode="after")
    def _paired(self) -> Self:
        if (self.error_type is None) != (self.certainty is None):
            msg = "an error type and its certainty are named together"
            raise ValueError(msg)
        if self.error_type is not None and self.message is not None:
            msg = "a classification names an error or what was not judged, not both"
            raise ValueError(msg)
        if self.model_role is not None and self.error_type is None:
            msg = "a model role is named only with the error its model holds"
            raise ValueError(msg)
        return self

    @property
    def judged(self) -> bool:
        return self.message is None


NO_ERROR = Classification()
REFERENCE_LONG = Classification(
    error_type="over_extended_model", certainty="medium", model_role="reference"
)


def _named(error_type: ErrorType, certainty: Certainty) -> Classification:
    return Classification(error_type=error_type, certainty=certainty)


def _unjudged(verdict: str, reason: str) -> Classification:
    return Classification(message=f"{verdict}: {reason}")


def _length(result: GeneLengthAudit) -> Classification:
    match (result.length_class, result.verdict):
        case ("SHORT", "GENOME_ENCODES"):
            return _named("truncated_model", "high")
        case ("SPLIT", "SPLIT_CONFIRMED"):
            return _named("split_model", "medium")
        case _:
            return NO_ERROR


_FUSIONS: dict[FusionVerdict, Classification] = {
    "EXTRA_MATCHES_NEIGHBOUR": _named("fused_model", "high"),
    "EXTRA_UNEXPLAINED": _named("over_extended_model", "low"),
    "NO_EXTRA": NO_ERROR,
}
_MISSING: dict[MissingVerdict, Classification] = {
    "IN_DNA_UNANNOTATED": _named("missing_gene", "high"),
    "IN_DNA_OTHER_MODEL": _named("missing_gene", "medium"),
    "PARTIAL": _named("missing_gene", "low"),
    "NOT_IN_DNA": NO_ERROR,
    "GAP": _unjudged(
        "GAP",
        "the absent genome has an assembly gap at the locus, so the check "
        "cannot judge whether its DNA holds the gene",
    ),
    "NO_SYNTENY": _unjudged(
        "NO_SYNTENY",
        "no conserved neighbours anchor the locus in the absent genome, "
        "so the check read no DNA",
    ),
    "ANNOTATED_IN_GENOME": _unjudged(
        "ANNOTATED_IN_GENOME",
        "the absent genome annotates members of the gene's ortholog group, "
        "so the gene is not missing",
    ),
}
_ORGANELLES: dict[OrganelleVerdict, Classification] = {
    "SPLIT_AT_JOIN": _named("organelle_split_at_join", "high"),
    "INTACT_ON_THE_LINE": NO_ERROR,
    "NOT_FOUND": _unjudged(
        "NOT_FOUND",
        "the contig encodes no whole copy of the reference protein, on the "
        "line or across the join, so the check cannot judge a split",
    ),
}


def _fusion(result: GeneFusionAudit) -> Classification:
    if result.fusion is not None:
        return _FUSIONS[result.fusion.verdict]
    unclassed = result.length_class == "UNQUALIFIED"
    why = (
        "the ortholog group cannot class the gene's length"
        if unclassed
        else "the gene is not LONG"
    )
    return _unjudged(
        result.length_class, f"{why}, so the fusion check reads no extra residues"
    )


def _paralogs(genes: list[str]) -> str:
    match genes:
        case [gene]:
            return f"the paralog {gene} lies"
        case _:
            return f"the paralogs {', '.join(genes)} lie"


def _unread_strain(result: StrainModelAudit) -> str:
    match result.not_read:
        case "NO_LOST_RUN":
            why = "the strain protein lacks no run of the reference protein"
        case "UNQUALIFIED":
            why = (
                "the pair's ortholog group is a residual group, not an orthology group"
            )
        case "PARALOG_IN_WINDOW":
            why = f"{_paralogs(result.nearby_paralogs)} in the window the check reads"
        case None:
            return (
                f"the strain's genome answers {result.dna.verdict} for the run its "
                "model lost, so the check judges no side"
            )
    return f"{why}, so the check reads no genome and judges no side"


def _strain(result: StrainModelAudit) -> Classification:
    match result.side:
        case "STRAIN_SHORT":
            return Classification(
                error_type="truncated_model",
                certainty="high",
                model_role="strain",
            )
        case "REFERENCE_LONG":
            return REFERENCE_LONG
        case "UNCLEAR":
            return NO_ERROR
        case "NO_RELATIVES":
            return _unjudged(
                "NO_RELATIVES",
                f"the ortholog group has no independent relatives "
                f"({result.relatives.missing}) to judge which side is wrong",
            )
        case "NOT_JUDGED":
            return _unjudged("NOT_JUDGED", _unread_strain(result))


def remodeled_by_side(
    error_type: ErrorType | None, side: SideVerdict | None
) -> Classification | None:
    match (error_type, side):
        case ("truncated_model", "REFERENCE_LONG"):
            return REFERENCE_LONG
        case _:
            return None


def _classify_targeted(
    confirmation: FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation,
) -> Classification:
    match confirmation:
        case FusionConfirmation(result=result):
            return _fusion(result)
        case StrainConfirmation(result=result):
            return _strain(result)
        case MissingGeneConfirmation(result=result):
            return _MISSING[result.verdict]
        case OrganelleConfirmation(result=result):
            return _ORGANELLES[result.verdict]


def classify_confirmation(
    confirmation: PseudogeneConfirmation
    | SelenoproteinConfirmation
    | LengthConfirmation
    | FusionConfirmation
    | StrainConfirmation
    | MissingGeneConfirmation
    | OrganelleConfirmation,
) -> Classification:
    match confirmation:
        case PseudogeneConfirmation(result=result):
            intact = result.verdict == "INTACT"
            return (
                _named("intact_gene_called_pseudogene", "high") if intact else NO_ERROR
            )
        case SelenoproteinConfirmation(result=result):
            stops = result.verdict == "STOPS_AT_SEC"
            return _named("sec_read_as_stop", "high") if stops else NO_ERROR
        case LengthConfirmation(result=result):
            return _length(result)
        case (
            FusionConfirmation()
            | StrainConfirmation()
            | MissingGeneConfirmation()
            | OrganelleConfirmation()
        ):
            return _classify_targeted(confirmation)


class ConfirmationEvidence(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["confirmation"] = "confirmation"
    confirmation: Confirmation


class RelativesEvidence(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["relatives"] = "relatives"
    reference_gene: str
    reference_length: int | None
    model_length: int | None
    relatives_median: float | None
    side: SideVerdict | None = None
    reference_organism: str | None = None


class GeneEvidencePayload(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["gene_evidence"] = "gene_evidence"
    genes: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[GeneEvidence, ...]

    @model_validator(mode="after")
    def _one_record_per_gene(self) -> Self:
        if len(self.genes) != len(self.evidence):
            msg = "gene evidence holds one record for each gene it read"
            raise ValueError(msg)
        return self


EvidencePayload = Annotated[
    ConfirmationEvidence | RelativesEvidence | GeneEvidencePayload,
    Field(discriminator="kind"),
]


class FindingTally(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    check: CheckName
    status: FindingStatus
    error_type: ErrorType | None
    judged: bool
    model_genome: str
    count: int = Field(ge=0)

    @model_validator(mode="after")
    def _error_when_confirmed(self) -> Self:
        if self.error_type is not None and self.status != "confirmed":
            msg = f"only a confirmed finding names an error, not a {self.status} one"
            raise ValueError(msg)
        if not self.judged and (self.status, self.error_type) != ("confirmed", None):
            msg = "only a confirmed finding that names no error can be not judged"
            raise ValueError(msg)
        return self

    @property
    def holds_error(self) -> bool:
        return self.error_type is not None and self.model_genome == self.genome


class FindingCounts(CamelModel):
    model_config = ConfigDict(frozen=True)

    screened: int = 0
    unsampled: int = 0
    trying: int = 0
    confirmed: int = 0
    failed: int = 0
    unreached: int = 0
    unread: int = 0
    errors: int = 0
    unjudged: int = 0


def counts_of(tally: Iterable[FindingTally]) -> FindingCounts:
    by_status: Counter[str] = Counter()
    for row in tally:
        by_status[row.status] += row.count
        if row.error_type is not None:
            by_status["errors"] += row.count
        if not row.judged:
            by_status["unjudged"] += row.count
    return FindingCounts.model_validate(by_status)


class AuditOutcome(CamelModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    status: RunStatus
    release: str | None
    requests: int
    unfinished: tuple[StageName, ...]
    counts: FindingCounts
    failed_genomes: tuple[str, ...]
    unreached_genomes: tuple[str, ...]
    unread_genomes: tuple[str, ...]
    halted: str | None = None
