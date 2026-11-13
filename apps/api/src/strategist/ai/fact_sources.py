"""The typed answers a statistic fact is read from, each schema checked when a toolset is built."""

from __future__ import annotations

from pydantic import BaseModel
from veupathdb_mcp.audit import (
    Anatomy,
    GeneEvidence,
    GeneLengthAudit,
    GenomeProvenance,
    IntronAudit,
    PseudogeneCallAudit,
    RateBounds,
    SelenoproteinEndAudit,
    StrainModelAudit,
)

from strategist.domain.audit.planning import ScopeProposal
from strategist.domain.audit.run_state import AuditOutcome
from strategist.domain.statistic_rows import fact_schema
from strategist.domain.strategy.computed_groups import ComparisonFacts
from strategist.services.audit.finding_views import FindingDetail, FindingPage
from strategist.services.audit.views import AuditRunSummary, AuditRunView

FACT_SOURCES: tuple[type[BaseModel], ...] = (
    Anatomy,
    GeneEvidence,
    GeneLengthAudit,
    GenomeProvenance,
    IntronAudit,
    PseudogeneCallAudit,
    RateBounds,
    SelenoproteinEndAudit,
    StrainModelAudit,
    AuditOutcome,
    AuditRunSummary,
    AuditRunView,
    FindingDetail,
    FindingPage,
    ScopeProposal,
    ComparisonFacts,
)


def warm_fact_schemas() -> None:
    for source in FACT_SOURCES:
        fact_schema(source)


__all__ = ["FACT_SOURCES", "warm_fact_schemas"]
