"""What the live aiExpression reporter answers, and what it never spends.

Every request here carries ``populateIfNotPresent: false``. The reporter
generates nothing, so the lane costs the deployment nothing.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict
from veupathdb.testing.summary import DriftLog
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionStatus,
)
from veupathdb.wdk.factory import get_wdk_client
from veupathdb.wdk.wdk_models import WDKSearchConfig
from veupathdb_mcp.wdk import (
    NO_SUMMARY_ON_THE_SITE,
    GeneExpressionSummary,
    extract_record_ids,
    get_gene_expression_summary,
)

from pathfinder.tests.live.conftest import Probe

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

SITE = "plasmodb"

# The site regenerates its summary cache, so no gene keeps one state. Each check
# reads these candidates and takes the first gene in the state it needs.
RECORDED_SUBJECTS = ("PF3D7_1133400", "PF3D7_0709000")
CANDIDATE_PAGE = 20


class ReporterStates(BaseModel):
    """One gene per cache state the site reports, read at run time."""

    model_config = ConfigDict(frozen=True)

    present: GeneExpressionSummary | None = None
    incomplete: GeneExpressionSummary | None = None
    candidates_read: int = 0


async def _candidate_genes() -> list[str]:
    """The subjects the client's fixtures record, then a page of the site's genes."""
    answer = await get_wdk_client(SITE).run_search_report(
        "transcript",
        "GenesByMolecularWeight",
        WDKSearchConfig(
            parameters={
                "organism": '["Plasmodium falciparum 3D7"]',
                "min_molecular_weight": "10000",
                "max_molecular_weight": "20000",
            }
        ),
        {
            "attributes": ["primary_key"],
            "tables": [],
            "pagination": {"offset": 0, "numRecords": CANDIDATE_PAGE},
        },
    )
    page = dict.fromkeys(extract_record_ids(answer.records))
    fresh = (gene for gene in page if gene not in RECORDED_SUBJECTS)
    return [*RECORDED_SUBJECTS, *fresh]


@pytest.fixture
async def reporter_states(wdk_identity: str) -> ReporterStates:
    """Read candidate genes until the site answers one of each cache state."""
    del wdk_identity
    present: GeneExpressionSummary | None = None
    incomplete: GeneExpressionSummary | None = None
    read = 0
    for gene in await _candidate_genes():
        found = await get_gene_expression_summary(SITE, gene)
        read += 1
        match found.result_status:
            case AiExpressionStatus.PRESENT if present is None:
                present = found
            case AiExpressionStatus.EXPERIMENTS_INCOMPLETE if incomplete is None:
                incomplete = found
        if present is not None and incomplete is not None:
            break
    return ReporterStates(present=present, incomplete=incomplete, candidates_read=read)


def _subject(
    found: GeneExpressionSummary | None,
    state: AiExpressionStatus,
    candidates_read: int,
) -> GeneExpressionSummary:
    """The gene the site holds in *state*, or a skip that names both."""
    if found is None:
        pytest.skip(
            f"{SITE} holds no gene in state {state.value} among the "
            f"{candidates_read} genes this check read"
        )
    return found


async def _reporter_status(probe: Probe, gene_id: str) -> int:
    """The status the reporter answers for one gene, generation never requested."""
    live = await probe(
        SITE,
        "POST",
        AI_EXPRESSION_REPORT_PATH,
        json={
            "searchConfig": {"parameters": {"primaryKeys": f"{gene_id},PlasmoDB"}},
            "reportConfig": {"populateIfNotPresent": False},
        },
    )
    return live.status


async def test_a_gene_the_site_has_summarized_carries_a_whole_summary(
    probe: Probe, drift_log: DriftLog, reporter_states: ReporterStates
) -> None:
    """A summarized gene answers 200, and every topic names its experiments."""
    found = _subject(
        reporter_states.present,
        AiExpressionStatus.PRESENT,
        reporter_states.candidates_read,
    )

    status = await _reporter_status(probe, found.gene_id)
    drift_log.record(
        site=SITE,
        check="ai-expression-status",
        subject=found.gene_id,
        expected=200,
        observed=status,
    )
    assert status == 200

    summary = found.summary
    assert summary is not None
    assert summary.headline != ""
    assert summary.one_paragraph_summary != ""
    assert len(summary.topics) > 0
    assert [topic.headline for topic in summary.topics if not topic.summaries] == []
    experiments = [entry for topic in summary.topics for entry in topic.summaries]
    assert [entry for entry in experiments if entry.dataset_id == ""] == []
    assert found.unavailable_reason is None
    # The site sends the experiment counts only beside a status it cannot summarize.
    assert (found.num_experiments, found.num_experiments_complete) == (None, None)


async def test_a_gene_with_experiments_outstanding_is_a_miss_and_not_a_failure(
    probe: Probe, drift_log: DriftLog, reporter_states: ReporterStates
) -> None:
    """A gene the site has not summarized answers 200 with no summary."""
    found = _subject(
        reporter_states.incomplete,
        AiExpressionStatus.EXPERIMENTS_INCOMPLETE,
        reporter_states.candidates_read,
    )

    status = await _reporter_status(probe, found.gene_id)
    drift_log.record(
        site=SITE,
        check="ai-expression-status",
        subject=found.gene_id,
        expected=200,
        observed=status,
    )
    assert status == 200

    assert found.summary is None
    assert found.unavailable_reason == NO_SUMMARY_ON_THE_SITE
    total = found.num_experiments
    complete = found.num_experiments_complete
    assert total is not None
    assert complete is not None
    assert total > 0
    assert complete < total


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
