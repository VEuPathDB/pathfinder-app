"""The gene models an audit finding's stored check result holds, in genome coordinates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator
from veupathdb_mcp.audit import (
    GeneSpan,
    IntronAudit,
    ModelSpans,
    SelenoproteinEndAudit,
    UnreadIntron,
)

from pathfinder.domain.audit.confirmations import (
    Confirmation,
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)

type Span = tuple[int, int]
GeneModelFigureKind = Literal[
    "intron", "length", "pseudogene", "strain", "merge", "sec_end"
]
ProposedKind = Literal["corrected", "retained"]


class KeptIntron(CamelModel):
    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    outcome: Literal["NONCANONICAL", "RETAINED"]
    motif: str | None
    depth_share: float | None
    covered_share: float | None
    track: str | None


class ProposedModel(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: ProposedKind
    gene: str
    exons: tuple[Span, ...]
    cds: tuple[Span, ...]
    removed_introns: tuple[Span, ...]
    junctions: tuple[Span, ...]
    junction_reads: tuple[int, ...]
    kept: tuple[KeptIntron, ...] = ()
    frame_kept: bool | None


class StopCodon(CamelModel):
    model_config = ConfigDict(frozen=True)

    gene: str
    seqid: str
    start: int
    end: int


class FindingModels(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: GeneModelFigureKind
    annotated: tuple[ModelSpans, ...] = Field(min_length=1)
    proposed: ProposedModel | None = None
    merged: GeneSpan | None = None
    stop: StopCodon | None = None

    @model_validator(mode="after")
    def _the_parts_of_its_kind(self) -> Self:
        if self.proposed is not None and self.kind != "intron":
            msg = "a finding holds a proposed model only for an intron check"
            raise ValueError(msg)
        if (self.merged is None) == (self.kind == "merge"):
            msg = (
                "a finding holds a merged span only for a merge, and a merge holds one"
            )
            raise ValueError(msg)
        if (self.stop is None) == (self.kind == "sec_end"):
            msg = (
                "a finding holds a stop codon only for a selenoprotein end, and that "
                "end holds one"
            )
            raise ValueError(msg)
        return self


def _merged(spans: Iterable[Span]) -> tuple[Span, ...]:
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def _kept_intron(intron: UnreadIntron) -> KeptIntron | None:
    depth = intron.depth
    match intron.outcome:
        case "NONCANONICAL" | "RETAINED" as outcome:
            return KeptIntron(
                start=intron.start,
                end=intron.end,
                outcome=outcome,
                motif=intron.motif,
                depth_share=None if depth is None else depth.depth_share,
                covered_share=None if depth is None else depth.covered_share,
                track=None if depth is None else depth.track,
            )
        case _:
            return None


def _kept(unread: Sequence[UnreadIntron]) -> tuple[KeptIntron, ...]:
    return tuple(k for k in map(_kept_intron, unread) if k is not None)


def _corrected(
    result: IntronAudit, unread: Sequence[UnreadIntron]
) -> ProposedModel | None:
    if result.corrected_cds is None:
        return None
    replacements = [j for intron in unread for j in intron.replacement]
    kept = _kept(unread)
    return ProposedModel(
        kind="corrected",
        gene=result.gene,
        exons=_merged([*result.corrected_cds, *((k.start, k.end) for k in kept)]),
        cds=tuple(result.corrected_cds),
        removed_introns=tuple((intron.start, intron.end) for intron in unread),
        junctions=tuple((j.start, j.end) for j in replacements),
        junction_reads=tuple(j.reads for j in replacements),
        kept=kept,
        frame_kept=result.frame_kept,
    )


def _retained(
    result: IntronAudit, model: ModelSpans, unread: Sequence[UnreadIntron]
) -> ProposedModel | None:
    kept = _kept(unread)
    if not kept:
        return None
    return ProposedModel(
        kind="retained",
        gene=result.gene,
        exons=_merged([*model.exons, *((k.start, k.end) for k in kept)]),
        cds=(),
        removed_introns=tuple((k.start, k.end) for k in kept),
        junctions=(),
        junction_reads=(),
        kept=kept,
        frame_kept=None,
    )


def _proposed(result: IntronAudit, model: ModelSpans) -> ProposedModel | None:
    unread = result.unread or []
    return _corrected(result, unread) or _retained(result, model, unread)


def stop_codon(model: ModelSpans) -> StopCodon:
    if model.strand == "+":
        end = max(last for _, last in model.cds)
        return StopCodon(gene=model.gene, seqid=model.seqid, start=end - 2, end=end)
    start = min(first for first, _ in model.cds)
    return StopCodon(gene=model.gene, seqid=model.seqid, start=start, end=start + 2)


def _read(models: Iterable[ModelSpans | None]) -> tuple[ModelSpans, ...]:
    return tuple(model for model in models if model is not None)


_FIGURES: Mapping[str, GeneModelFigureKind] = {
    "gene_length": "length",
    "gene_split": "length",
    "pseudogene_call": "pseudogene",
    "strain_model": "strain",
}


def _annotated(confirmation: Confirmation) -> tuple[ModelSpans, ...]:
    match confirmation:
        case IntronConfirmation(result=result):
            return _read([result.model])
        case PseudogeneConfirmation(result=result):
            return _read([result.reference_model])
        case (
            LengthConfirmation(result=read)
            | StrainConfirmation(result=read)
            | FusionConfirmation(result=read)
            | SelenoproteinConfirmation(result=read)
        ):
            return _read(read.models)
        case _:
            return ()


def finding_models(confirmation: Confirmation) -> FindingModels | None:
    annotated = _annotated(confirmation)
    if not annotated:
        return None
    match confirmation:
        case IntronConfirmation(result=result):
            proposed = _proposed(result, annotated[0])
            return FindingModels(kind="intron", annotated=annotated, proposed=proposed)
        case FusionConfirmation(result=result):
            return FindingModels(
                kind="merge", annotated=annotated, merged=result.merged
            )
        case SelenoproteinConfirmation(
            result=SelenoproteinEndAudit(models=[ModelSpans() as gene, *_])
        ):
            return FindingModels(
                kind="sec_end", annotated=annotated, stop=stop_codon(gene)
            )
        case SelenoproteinConfirmation():
            return None
        case _:
            return FindingModels(kind=_FIGURES[confirmation.check], annotated=annotated)
