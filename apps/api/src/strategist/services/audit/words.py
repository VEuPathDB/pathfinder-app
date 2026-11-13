from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict
from veupathdb_mcp.audit import EVIDENCE_TABLES

from strategist.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_DESCRIPTIONS,
    ERROR_TYPE_TITLES,
    EVIDENCE_KIND_TITLES,
    EVIDENCE_STATUS_SENTENCES,
    HALT_SENTENCES,
    LITERATURE_SENTENCES,
    NO_RELATIVES_SENTENCES,
    REVIEW_STATUS_SENTENCES,
    UNCHECKED_SENTENCES,
    UNRESOLVED_WORDS,
    VERDICT_KIND_SENTENCES,
)

_TABLE = ConfigDict(frozen=True, extra="forbid")


class CheckWords(BaseModel):
    model_config = _TABLE

    pseudogene_call: str
    selenoprotein_end: str
    gene_length: str
    gene_split: str
    gene_fusion: str
    strain_model: str
    missing_gene: str
    organelle_join: str
    intron_support: str


class ErrorTypeWords(BaseModel):
    model_config = _TABLE

    intact_gene_called_pseudogene: str
    sec_read_as_stop: str
    truncated_model: str
    sequence_frameshift: str
    part_in_other_frame: str
    possible_missed_exon: str
    split_model: str
    over_extended_model: str
    fused_model: str
    missing_gene: str
    organelle_split_at_join: str
    missing_exon: str
    shifted_splice_site: str
    spurious_intron: str
    unsupported_intron: str


class FindingStatusWords(BaseModel):
    model_config = _TABLE

    screened: str
    unsampled: str
    trying: str
    confirmed: str
    failed: str
    declined: str
    unreached: str
    unread: str


class UnresolvedWords(BaseModel):
    model_config = _TABLE

    screened: str
    unsampled: str
    trying: str
    failed: str
    declined: str
    unreached: str
    unread: str


class HaltWords(BaseModel):
    model_config = _TABLE

    sign_in: str
    task_failed: str


class VerdictKindWords(BaseModel):
    model_config = _TABLE

    error: str
    no_error: str
    undecided: str


class LiteratureWords(BaseModel):
    model_config = _TABLE

    known: str
    not_found: str
    not_searched: str


class ReviewStatusWords(BaseModel):
    model_config = _TABLE

    waiting: str
    reviewing: str
    synthesized: str
    stopped: str


class EvidenceKindWords(BaseModel):
    model_config = _TABLE

    confirmation: str
    relatives: str
    gene_evidence: str


class EvidenceStatusWords(BaseModel):
    model_config = _TABLE

    pending: str
    trying: str
    stored: str
    failed: str
    unreached: str
    unread: str


class NoRelativesWords(BaseModel):
    model_config = _TABLE

    RESIDUAL_GROUP: str
    PARALOGS: str
    FEWER_THAN_TWO: str


class AuditWords(CamelModel):
    model_config = ConfigDict(frozen=True)

    checks: CheckWords
    error_types: ErrorTypeWords
    error_descriptions: ErrorTypeWords
    finding_statuses: FindingStatusWords
    unresolved: UnresolvedWords
    halts: HaltWords
    verdict_kinds: VerdictKindWords
    literature: LiteratureWords
    review_statuses: ReviewStatusWords
    evidence_kinds: EvidenceKindWords
    evidence_statuses: EvidenceStatusWords
    no_relatives: NoRelativesWords
    evidence_tables: tuple[str, ...]


AUDIT_WORDS = AuditWords(
    checks=CheckWords.model_validate(CHECK_TITLES),
    error_types=ErrorTypeWords.model_validate(ERROR_TYPE_TITLES),
    error_descriptions=ErrorTypeWords.model_validate(ERROR_TYPE_DESCRIPTIONS),
    finding_statuses=FindingStatusWords.model_validate(UNCHECKED_SENTENCES),
    unresolved=UnresolvedWords.model_validate(UNRESOLVED_WORDS),
    halts=HaltWords.model_validate(HALT_SENTENCES),
    verdict_kinds=VerdictKindWords.model_validate(VERDICT_KIND_SENTENCES),
    literature=LiteratureWords.model_validate(LITERATURE_SENTENCES),
    review_statuses=ReviewStatusWords.model_validate(REVIEW_STATUS_SENTENCES),
    evidence_kinds=EvidenceKindWords.model_validate(EVIDENCE_KIND_TITLES),
    evidence_statuses=EvidenceStatusWords.model_validate(EVIDENCE_STATUS_SENTENCES),
    no_relatives=NoRelativesWords.model_validate(NO_RELATIVES_SENTENCES),
    evidence_tables=EVIDENCE_TABLES,
)
