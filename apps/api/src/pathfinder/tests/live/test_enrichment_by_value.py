"""Whether a live site still names its enrichment columns as pinned.

An enrichment plugin owns its own column names and a wrong one yields an empty
column rather than an error (WDK-ANS-007), so an identity that arrives empty is
the drift signal. One run serves the whole check, and its duration is recorded
for the call budget.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import pytest
from veupathdb.testing import DriftLog
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.wdk import fetch_gene_ids_from_step
from veupathdb_mcp.wdk.enrichment import (
    MAX_ENRICHMENT_GENE_IDS,
    BackgroundSource,
    enrich_gene_ids_by_value,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_ORGANISM = "Plasmodium falciparum 3D7"

_PINNED_COLUMNS = {
    "go_function": ("goId", "goTerm"),
    "go_component": ("goId", "goTerm"),
    "go_process": ("goId", "goTerm"),
    "pathway": ("pathwayId", "pathwayName"),
    "word": ("word", "pathwayName"),
}

# GO and word annotations cover any sizeable falciparum set. Pathway coverage
# is sparse, so its term count is recorded and not required.
_MUST_YIELD_TERMS = ("go_process", "word")

_PLUGIN_OUTAGES = frozenset({"word"})
"""Analyses the sites answer ERROR for. An outage is not a column that drifted."""


async def test_a_gene_list_enriches_through_the_pinned_columns(
    owned_strategy: Callable[[str], Awaitable[tuple[int, int]]],
    drift_log: DriftLog,
) -> None:
    _, step_id = await owned_strategy(_SITE)
    rows = await fetch_gene_ids_from_step(get_strategy_api(_SITE), step_id=step_id)
    # A transcript step lists one row per transcript, so a gene repeats across
    # its transcripts. Enrichment counts genes, so the list holds each one once.
    genes = list(dict.fromkeys(rows))[:MAX_ENRICHMENT_GENE_IDS]
    assert len(genes) == MAX_ENRICHMENT_GENE_IDS

    started = time.monotonic()
    result = await enrich_gene_ids_by_value(
        _SITE, genes, BackgroundSource(organism=_ORGANISM)
    )
    drift_log.record(
        site=_SITE,
        check="enrich_gene_ids",
        subject=f"seconds for {len(genes)} genes",
        observed=round(time.monotonic() - started, 1),
    )

    assert result.gene_count == len(genes)
    assert {a.analysis_type for a in result.analyses} == set(_PINNED_COLUMNS)

    unavailable = {a.analysis_type for a in result.analyses if a.error is not None}
    drift_log.record(
        site=_SITE,
        check="enrich_gene_ids",
        subject="analyses the site could not complete",
        observed=", ".join(sorted(unavailable)) or "none",
        expected=", ".join(sorted(_PLUGIN_OUTAGES)) or "none",
    )
    assert unavailable <= _PLUGIN_OUTAGES

    for analysis in [a for a in result.analyses if a.error is None]:
        columns = analysis.source_columns
        term_id, term_name = _PINNED_COLUMNS[analysis.analysis_type]
        drift_log.record(
            site=_SITE,
            check="enrich_gene_ids",
            subject=f"{analysis.analysis_type} columns",
            observed=f"{columns.envelope}.{columns.term_id}/{columns.term_name}",
            expected=f"resultData.{term_id}/{term_name}",
        )
        drift_log.record(
            site=_SITE,
            check="enrich_gene_ids",
            subject=f"{analysis.analysis_type} terms",
            observed=len(analysis.terms),
        )

        assert columns.envelope == "resultData"
        assert (columns.term_id, columns.term_name) == (term_id, term_name)
        assert all(t.term_id and t.term_name for t in analysis.terms)
        if analysis.analysis_type in _MUST_YIELD_TERMS:
            assert analysis.terms

    go = [a for a in result.analyses if a.analysis_type == "go_process"]
    assert all(t.term_id.startswith("GO:") for a in go for t in a.terms)
