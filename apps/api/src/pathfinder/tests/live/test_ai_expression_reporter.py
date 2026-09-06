"""What the live aiExpression reporter answers, and what it never spends.

Every request here carries ``populateIfNotPresent: false``. The reporter
generates nothing, so the lane costs the deployment nothing.
"""

from __future__ import annotations

import pytest
from veupathdb.testing.summary import DriftLog
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionStatus,
)
from veupathdb_mcp.wdk.ai_expression import (
    NO_SUMMARY_ON_THE_SITE,
    get_gene_expression_summary,
)

from pathfinder.tests.live.conftest import Probe

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

SITE = "plasmodb"
CACHED_GENE = "PF3D7_1133400"
UNCACHED_GENE = "PF3D7_0709000"


async def test_a_gene_with_every_experiment_cached_answers_two_hundred(
    probe: Probe, drift_log: DriftLog
) -> None:
    """The reporter answers, and every experiment entry the site holds is present."""
    live = await probe(
        SITE,
        "POST",
        AI_EXPRESSION_REPORT_PATH,
        json={
            "searchConfig": {"parameters": {"primaryKeys": f"{CACHED_GENE},PlasmoDB"}},
            "reportConfig": {"populateIfNotPresent": False},
        },
    )

    drift_log.record(
        site=SITE,
        check="ai-expression-status",
        subject=CACHED_GENE,
        expected=200,
        observed=live.status,
    )
    assert live.status == 200

    found = await get_gene_expression_summary(SITE, CACHED_GENE)
    assert found.gene_id == CACHED_GENE
    assert found.num_experiments == found.num_experiments_complete
    assert found.num_experiments > 0


async def test_a_gene_with_nothing_cached_is_a_miss_and_not_a_failure(
    probe: Probe, drift_log: DriftLog
) -> None:
    """A gene the site has not summarized answers 200 with no summary."""
    live = await probe(
        SITE,
        "POST",
        AI_EXPRESSION_REPORT_PATH,
        json={
            "searchConfig": {
                "parameters": {"primaryKeys": f"{UNCACHED_GENE},PlasmoDB"}
            },
            "reportConfig": {"populateIfNotPresent": False},
        },
    )

    drift_log.record(
        site=SITE,
        check="ai-expression-status",
        subject=UNCACHED_GENE,
        expected=200,
        observed=live.status,
    )
    assert live.status == 200

    found = await get_gene_expression_summary(SITE, UNCACHED_GENE)
    assert found.summary is None
    assert found.unavailable_reason == NO_SUMMARY_ON_THE_SITE
    assert found.result_status is AiExpressionStatus.EXPERIMENTS_INCOMPLETE


async def test_a_gene_the_site_does_not_hold_is_refused_by_its_primary_key(
    probe: Probe, drift_log: DriftLog
) -> None:
    """A source id no site record carries is a 422 that names the key."""
    live = await probe(
        SITE,
        "POST",
        AI_EXPRESSION_REPORT_PATH,
        json={
            "searchConfig": {"parameters": {"primaryKeys": "NOT_A_GENE,PlasmoDB"}},
            "reportConfig": {"populateIfNotPresent": False},
        },
    )

    drift_log.record(
        site=SITE,
        check="ai-expression-unknown-gene",
        subject="NOT_A_GENE",
        expected=422,
        observed=live.status,
    )
    assert live.status == 422
    assert "primaryKeys" in live.text
