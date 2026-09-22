"""One step of a thread's strategy answers its genes, one page at a time."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKFilterValue

from pathfinder.platform.errors import AppError, ErrorCode, NotFoundError
from pathfinder.services.conversations import step_records
from pathfinder.services.conversations.responses import (
    StepRecord,
    StepRecordsResponse,
)
from pathfinder.tests._support.step_answers import (
    GENE_TOTAL,
    PUSHED_STEP,
    SITE,
    UNPUSHED_STEP,
    WDK_STEP_ID,
    AnswerRead,
    SiteApi,
    thread,
)

_GENE_VIEW = [WDKFilterValue(name="representativeTranscriptOnly", value={})]


def _install(
    monkeypatch: pytest.MonkeyPatch, *, record_type: str = "transcript"
) -> SiteApi:
    stored = thread(record_type=record_type)
    api = SiteApi()

    async def _owned(*_args: Any, **_kwargs: Any) -> Any:
        return stored

    monkeypatch.setattr(step_records, "get_owned_thread_or_404", _owned)
    monkeypatch.setattr(step_records, "get_strategy_api", lambda _site_id: api)
    return api


async def _read(step_id: str, *, offset: int = 0, limit: int = 50) -> Any:
    stored = thread()
    return await step_records.read_step_records(
        AsyncSession(),
        stored[0].id,
        stored[0].user_id,
        site_id=SITE,
        page=step_records.StepPage(step_id=step_id, offset=offset, limit=limit),
    )


async def test_a_pushed_step_answers_its_genes_and_the_site_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)

    found = await _read(PUSHED_STEP)

    assert found == StepRecordsResponse(
        step_id=PUSHED_STEP,
        wdk_step_id=WDK_STEP_ID,
        total=GENE_TOTAL,
        offset=0,
        limit=50,
        record_type="transcript",
        step_url="https://toxodb.org/toxo/app/workspace/strategies/900/11",
        records=[
            StepRecord(
                gene_id="TGME49_200010",
                organism="Toxoplasma gondii ME49",
                product="dense granule protein GRA20",
                record_url="https://toxodb.org/toxo/app/record/gene/TGME49_200010",
            ),
            StepRecord(
                gene_id="TGME49_200130",
                organism="Toxoplasma gondii ME49",
                product="Toxoplasma gondii family C protein",
                record_url="https://toxodb.org/toxo/app/record/gene/TGME49_200130",
            ),
        ],
    )


async def test_a_transcript_step_is_read_one_row_per_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page and the offset count genes, as the total does."""
    api = _install(monkeypatch)

    await _read(PUSHED_STEP, offset=100, limit=25)

    assert api.reads == [
        AnswerRead(
            step_id=WDK_STEP_ID,
            attributes=["primary_key", "organism", "gene_product"],
            pagination={"offset": 100, "numRecords": 25},
            view_filters=_GENE_VIEW,
        )
    ]


async def test_a_gene_step_reads_the_gene_product_with_no_view_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch, record_type="gene")

    await _read(PUSHED_STEP)

    assert api.reads == [
        AnswerRead(
            step_id=WDK_STEP_ID,
            attributes=["primary_key", "organism", "product"],
            pagination={"offset": 0, "numRecords": 50},
            view_filters=None,
        )
    ]


async def test_a_step_not_on_the_site_is_a_conflict_and_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch)

    with pytest.raises(AppError) as refusal:
        await _read(UNPUSHED_STEP)

    assert (refusal.value.code, refusal.value.status) == (
        ErrorCode.INVALID_STRATEGY,
        409,
    )
    assert refusal.value.detail == (
        f"Step {UNPUSHED_STEP!r} is not on the site yet, so it has no results."
    )
    assert api.reads == []


async def test_a_step_the_graph_does_not_hold_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch)

    with pytest.raises(NotFoundError) as refusal:
        await _read("step_elsewhere")

    assert refusal.value.code == ErrorCode.STEP_NOT_FOUND
    assert api.reads == []


async def test_a_strategy_of_records_that_are_not_genes_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch, record_type="compound")

    with pytest.raises(ValidationError) as refusal:
        await _read(PUSHED_STEP)

    assert refusal.value.detail == "A compound record is not a gene."
    assert api.reads == []
