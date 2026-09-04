"""Enrichment domain types.

Pure type definitions for enrichment analysis results. This module
is a leaf — it imports only from ``platform.pydantic_base``.
"""

from typing import Literal

from assistant_core.platform.pydantic_base import (
    CamelModel,
    NonFiniteToNone,
    NonFiniteToNoneRounded,
)
from pydantic import ConfigDict, Field

type EnrichmentAnalysisType = Literal[
    "go_function", "go_component", "go_process", "pathway", "word"
]

ALL_ENRICHMENT_ANALYSIS_TYPES: tuple[EnrichmentAnalysisType, ...] = (
    "go_function",
    "go_component",
    "go_process",
    "pathway",
    "word",
)


class BackgroundSource(CamelModel):
    """The annotated genome an over-representation test runs against.

    The enrichment plugins restrict both the result and the background to one
    organism. A None organism keeps the one the analysis form offers.
    """

    model_config = ConfigDict(frozen=True)

    organism: str | None = None


class EnrichmentTerm(CamelModel):
    """Single enriched term from WDK analysis.

    WDK returns numeric fields as JSON strings (``"3.48"``, ``"3.40e-13"``,
    ``"Infinity"``). A None ratio is unbounded; a None probability is not
    computable.
    """

    model_config = ConfigDict(frozen=True)

    term_id: str
    term_name: str
    gene_count: int
    background_count: int
    fold_enrichment: NonFiniteToNoneRounded
    odds_ratio: NonFiniteToNoneRounded
    p_value: NonFiniteToNone
    fdr: NonFiniteToNone
    bonferroni: NonFiniteToNone
    genes: list[str] = Field(default_factory=list)


class EnrichmentResult(CamelModel):
    """Results for a single enrichment analysis type."""

    model_config = ConfigDict(frozen=True)

    analysis_type: EnrichmentAnalysisType
    terms: list[EnrichmentTerm]
    total_genes_analyzed: int = 0
    background_size: int = 0
    error: str | None = None
