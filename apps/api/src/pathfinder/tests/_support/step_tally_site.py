"""A site and a tool server that answer one built step's column counts."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import JsonValue
from veupathdb.errors import validate_response
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKRecordType, WDKWordCounts
from veupathdb_mcp.wdk import ColumnCounts, StepColumns

from pathfinder.services.experiment import step_tally
from pathfinder.services.experiment.step_tally import CountedStep
from pathfinder.tests._support.ortho_taxonomy import recorded_ortho_taxonomy
from pathfinder.tests._support.qa_recording import SUITE_WDK_STORE, qa_recording

STEP = 227284080
STEP_URL = "https://qa.orthomcl.org/orthomcl.qa/app/workspace/strategies/1/227284080"


def counted_step(
    record_type: str,
    search_name: str,
    noun: str,
    step_url: str | None = None,
    refused: frozenset[str] = frozenset(),
) -> CountedStep:
    return CountedStep(
        site_id="orthomcl",
        wdk_step_id=STEP,
        record_type=record_type,
        search_name=search_name,
        record_noun=noun,
        step_url=step_url,
        refused=refused,
    )


def _recorded(name: str) -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        qa_recording(SUITE_WDK_STORE / name).read_text()
    )


def sequence_record_type() -> WDKRecordType:
    return WDKRecordType.model_validate(
        _recorded("orthomcl_sequence_record_type.json").body
    )


def singleton_counts() -> WDKWordCounts:
    return WDKWordCounts.model_validate(
        _recorded("orthomcl_singleton_word_counts.json").body
    )


class TallySite:
    def __init__(
        self, record_type: WDKRecordType, *, step_count: int, words: JsonValue = None
    ) -> None:
        self.record_type = record_type
        self.step_count = step_count
        self.words = words
        self.reports: list[tuple[int, str]] = []

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        assert record_type == self.record_type.url_segment
        return self.record_type

    async def get_step_word_counts(self, step_id: int, reporter: str) -> WDKWordCounts:
        self.reports.append((step_id, reporter))
        return validate_response(
            WDKWordCounts, self.words, f"{reporter} report for step {step_id}"
        )

    async def get_step_count(self, step_id: int) -> int:
        assert step_id == STEP
        return self.step_count


@dataclass
class ToolServer:
    """The tool server's column reads: one answer or one refusal for each."""

    counts: ColumnCounts | None = None
    refusal: Exception | None = None
    listed: StepColumns | None = None
    counted: list[tuple[str, int, str, int]] = field(default_factory=list)
    listed_for: list[tuple[str, int]] = field(default_factory=list)

    async def count_by_column(
        self,
        site_id: str,
        step_id: int,
        column: str,
        top: int = 20,
        *,
        budget_seconds: float | None = None,
    ) -> ColumnCounts:
        assert budget_seconds is None
        self.counted.append((site_id, step_id, column, top))
        if self.refusal is not None:
            raise self.refusal
        assert self.counts is not None
        return self.counts

    async def list_step_columns(self, site_id: str, step_id: int) -> StepColumns:
        self.listed_for.append((site_id, step_id))
        assert self.listed is not None
        return self.listed


def serve(
    monkeypatch: pytest.MonkeyPatch, site: TallySite, server: ToolServer
) -> TallySite:
    tree = recorded_ortho_taxonomy()
    names = {node.code: node.label for node in tree.nodes() if not node.clade}

    async def genome_names(site_id: str) -> dict[str, str]:
        del site_id
        return names

    monkeypatch.setattr(step_tally, "get_strategy_api", lambda _site_id: site)
    monkeypatch.setattr(step_tally, "genome_names", genome_names)
    monkeypatch.setattr(step_tally, "count_by_column", server.count_by_column)
    monkeypatch.setattr(step_tally, "list_step_columns", server.list_step_columns)
    return site
