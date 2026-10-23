"""What one audit run examines: a site, the genomes it screens, the gene targets it checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

CheckName = Literal[
    "pseudogene_call",
    "selenoprotein_end",
    "gene_length",
    "gene_split",
    "gene_fusion",
    "strain_model",
    "missing_gene",
    "organelle_join",
]
ScreenedCheck = Literal["gene_length", "gene_split", "pseudogene_call"]
GenomeRole = Literal["audited", "comparison"]
GenomeStatus = Literal[
    "pending", "trying", "collected", "failed", "unreached", "unread"
]
GeneName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
OrganismName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]

MAX_UNNAMED_GENOME_TARGETS = 8
MAX_COMPARISON_GENOMES = 40
MAX_TARGETS = 200
DEFAULT_CONFIRM_LIMIT = 150
MAX_CONFIRM_LIMIT = 500
ADMITTED_GENOMES = "audit_max_genomes"


def _escaped(name: str) -> str:
    return name.replace("%", "%25").replace(":", "%3A").replace("+", "%2B")


def target_key(check: str, genes: Sequence[str], *qualifiers: str) -> str:
    named = "+".join(_escaped(gene) for gene in genes)
    return ":".join([check, named, *(_escaped(q) for q in qualifiers)])


class SingleGeneTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["gene_length", "gene_fusion"]
    genes: tuple[GeneName]

    @property
    def key(self) -> str:
        return target_key(self.check, self.genes)

    @property
    def genome(self) -> None:
        return None

    @property
    def whole_genome(self) -> None:
        return None

    @property
    def reads_unnamed_genome(self) -> bool:
        return self.check == "gene_fusion"


class GenePairTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["pseudogene_call", "selenoprotein_end", "gene_split", "strain_model"]
    genes: tuple[GeneName, GeneName]

    @field_validator("genes")
    @classmethod
    def _split_in_one_order(
        cls, genes: tuple[str, str], info: ValidationInfo
    ) -> tuple[str, str]:
        match info.data:
            case {"check": "gene_split"}:
                first, second = sorted(genes)
                return (first, second)
            case _:
                return genes

    @model_validator(mode="after")
    def _two_genes(self) -> Self:
        if self.genes[0] == self.genes[1]:
            msg = f"{self.check} names {self.genes[0]} twice"
            raise ValueError(msg)
        return self

    @property
    def key(self) -> str:
        return target_key(self.check, self.genes)

    @property
    def genome(self) -> None:
        return None

    @property
    def whole_genome(self) -> None:
        return None

    @property
    def reads_unnamed_genome(self) -> bool:
        return False


class MissingGeneTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["missing_gene"]
    genes: tuple[GeneName]
    absent_organism: OrganismName

    @property
    def key(self) -> str:
        return target_key(self.check, self.genes, self.absent_organism)

    @property
    def genome(self) -> str:
        return self.absent_organism

    @property
    def whole_genome(self) -> str:
        return self.absent_organism

    @property
    def reads_unnamed_genome(self) -> bool:
        return True


class OrganelleTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: Literal["organelle_join"]
    genes: tuple[GeneName]
    organism: OrganismName
    sequence_id: GeneName

    @property
    def key(self) -> str:
        return target_key(self.check, self.genes, self.organism, self.sequence_id)

    @property
    def genome(self) -> str:
        return self.organism

    @property
    def whole_genome(self) -> str:
        return self.organism

    @property
    def reads_unnamed_genome(self) -> bool:
        return False


GeneTarget = Annotated[
    SingleGeneTarget | GenePairTarget | MissingGeneTarget | OrganelleTarget,
    Field(discriminator="check"),
]


class AdmissionContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    audit_max_genomes: int | None = None


def _repeated(names: Sequence[str]) -> list[str]:
    return sorted({name for name in names if names.count(name) > 1})


class AuditScope(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str = Field(min_length=1)
    genomes: tuple[OrganismName, ...] = ()
    comparison: tuple[OrganismName, ...] = Field(
        default=(), max_length=MAX_COMPARISON_GENOMES
    )
    checks: tuple[ScreenedCheck, ...] = ()
    targets: tuple[GeneTarget, ...] = Field(default=(), max_length=MAX_TARGETS)
    reference_genome: OrganismName | None = None
    confirm_limit: int = Field(
        default=DEFAULT_CONFIRM_LIMIT, ge=1, le=MAX_CONFIRM_LIMIT
    )

    @model_validator(mode="after")
    def _explicit(self) -> Self:
        if not self.genomes and not self.targets:
            msg = "an audit names the genomes it screens or the gene targets it checks"
            raise ValueError(msg)
        if bool(self.genomes) != bool(self.checks):
            msg = "a screened genome needs a check, and a check needs a screened genome"
            raise ValueError(msg)
        if self.comparison and not self.genomes:
            msg = "comparison genomes serve a screened genome"
            raise ValueError(msg)
        repeated = _repeated(
            [*self.collected, *self.checks, *(t.key for t in self.targets)]
        )
        if repeated:
            msg = f"{', '.join(repeated)} is named twice"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _reference(self) -> Self:
        screens_calls = "pseudogene_call" in self.checks
        if screens_calls and self.reference_genome is None:
            msg = "a pseudogene screen names its reference genome"
            raise ValueError(msg)
        if not screens_calls and self.reference_genome is not None:
            msg = "a reference genome serves a pseudogene screen"
            raise ValueError(msg)
        if screens_calls and self.reference_genome not in self.collected:
            msg = "the reference genome is one of the collected genomes"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _genome_reads(self, info: ValidationInfo) -> Self:
        unnamed = sum(t.reads_unnamed_genome for t in self.targets)
        if unnamed > MAX_UNNAMED_GENOME_TARGETS:
            msg = (
                f"an audit holds at most {MAX_UNNAMED_GENOME_TARGETS} fusion and "
                f"missing-gene targets, not {unnamed}"
            )
            raise ValueError(msg)
        cap = AdmissionContext.model_validate(info.context or {}).audit_max_genomes
        read = len(whole_genome_reads(self))
        if cap is not None and read > cap:
            msg = f"an audit reads at most {cap} whole genomes, not {read}"
            raise ValueError(msg)
        return self

    @classmethod
    def admitted(cls, raw: Mapping[str, object], *, max_genomes: int) -> AuditScope:
        return cls.model_validate(raw, context={ADMITTED_GENOMES: max_genomes})

    @property
    def collected(self) -> tuple[str, ...]:
        return (*self.genomes, *self.comparison)

    @property
    def roles(self) -> list[tuple[str, GenomeRole]]:
        audited: list[tuple[str, GenomeRole]] = [
            (name, "audited") for name in self.genomes
        ]
        compared: list[tuple[str, GenomeRole]] = [
            (name, "comparison") for name in self.comparison
        ]
        return [*audited, *compared]


def whole_genome_reads(scope: AuditScope) -> frozenset[str]:
    named = (
        *scope.genomes,
        scope.reference_genome,
        *(t.whole_genome for t in scope.targets),
    )
    return frozenset(name for name in named if name is not None)


def paired_genome(target: GeneTarget, organisms: Mapping[str, str]) -> str | None:
    match target:
        case GenePairTarget(check="strain_model", genes=(_, reference)):
            return organisms.get(reference)
        case _:
            return None
