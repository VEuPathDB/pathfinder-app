from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic_ai import ToolFailed
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKSortSpec

from pathfinder.ai.tools.standalone import _sample_page, results
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_TOTAL = 523_795
_ASKED = ["gene_product", "evalue"]


class _Step:
    def __init__(self, *, refused: frozenset[str], broken_at: int | None) -> None:
        self.refused = refused
        self.broken_at = broken_at
        self.asked: list[list[str] | None] = []

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: list[WDKSortSpec] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del step_id, tables, sorting, view_filters
        self.asked.append(attributes)
        if len(self.asked) - 1 == self.broken_at:
            msg = "POST /users/1/steps/42/reports/standard -> HTTP 500: Internal Error"
            raise WDKError(msg, status=500)
        named = [name for name in attributes or [] if name in self.refused]
        if named:
            msg = (
                "POST /users/1/steps/42/reports/standard -> HTTP 400: "
                f"Attribute '{named[0]}' is not available for question "
                "'GeneQuestions.GenesByTaxon'"
            )
            raise WDKError(msg, status=400)
        page = pagination or {}
        offset, wanted = page.get("offset", 0), page.get("numRecords", 0)
        shown = attributes or []
        return WDKAnswer.model_validate(
            {
                "meta": {"displayTotalCount": _TOTAL, "attributes": shown},
                "records": [
                    {
                        "displayName": f"G{gene}",
                        "id": [{"name": "source_id", "value": f"G{gene}"}],
                        "attributes": {name: f"{name} {gene}" for name in shown},
                    }
                    for gene in range(offset, offset + wanted)
                ],
            }
        )


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    *,
    refused: frozenset[str] = frozenset(),
    broken_at: int | None = None,
) -> _Step:
    step = _Step(refused=refused, broken_at=broken_at)
    monkeypatch.setattr(_sample_page, "get_strategy_api", lambda site_id: step)
    return step


async def _sample(attributes: list[str] | None) -> _sample_page.SampledRecords:
    return await _sample_page.sample_page(
        "vectorbase",
        42,
        limit=100,
        attributes=attributes,
        record_type="transcript",
        seed="m:42",
    )


async def test_an_attribute_every_report_refuses_is_dropped_after_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, refused=frozenset({"evalue"}))

    sampled = await _sample(_ASKED)

    assert step.asked == [
        None,
        ["gene_product", "evalue"],
        ["gene_product"],
        ["gene_product"],
        ["gene_product"],
        ["gene_product"],
    ]
    assert sampled.result.attributes == ["gene_product"]
    assert sampled.result.dropped_attributes == ["evalue"]
    assert len(sampled.result.records) == 100
    assert {tuple(row) for row in sampled.result.records} == {("id", "gene_product")}


async def test_the_rows_carry_the_kept_attributes_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, refused=frozenset({"evalue"}))

    sampled = await _sample(_ASKED)

    assert [
        row["gene_product"] == f"gene_product {str(row['id']).removeprefix('G')}"
        for row in sampled.result.records
    ] == [True] * 100


async def test_a_second_refused_attribute_reads_the_ids_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, refused=frozenset(_ASKED))

    sampled = await _sample(_ASKED)

    assert step.asked == [None, _ASKED, ["evalue"], None, None, None, None]
    assert sampled.result.attributes == []
    assert sampled.result.dropped_attributes == ["gene_product", "evalue"]
    assert {tuple(row) for row in sampled.result.records} == {("id",)}
    assert len(sampled.gene_ids) == 100


async def test_the_tool_names_the_attribute_the_site_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def asked(*_: object, own_search: str | None) -> list[str]:
        del own_search
        return ["evalue"]

    monkeypatch.setattr(results, "sample_attributes", asked)
    _serve(monkeypatch, refused=frozenset({"evalue"}))

    sample = returned(
        await results.get_sample_records(
            agent_run_context(site_id="vectorbase"), 42, limit=100
        ),
        _sample_page.StepSample,
    )

    assert sample.dropped_attributes == ["evalue"]
    assert "evalue" not in sample.attributes
    assert len(sample.records) == 100


async def test_a_refusal_with_no_attributes_asked_fails_the_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, broken_at=1)

    with pytest.raises(WDKError):
        await _sample(None)

    assert step.asked == [None, None]


async def test_a_server_error_fails_the_sample_and_is_not_read_without_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch, broken_at=3)

    with pytest.raises(WDKError) as broken:
        await _sample(_ASKED)

    assert broken.value.status == 500
    assert step.asked == [None, _ASKED, _ASKED, _ASKED]


async def test_a_server_error_is_a_failed_read_with_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def asked(*_: object, own_search: str | None) -> list[str]:
        del own_search
        return []

    monkeypatch.setattr(results, "sample_attributes", asked)
    _serve(monkeypatch, broken_at=2)
    ctx = agent_run_context(site_id="vectorbase")

    with pytest.raises(ToolFailed) as failed:
        await results.get_sample_records(ctx, 42, limit=100)

    assert "got no answer from the site (HTTP 500" in str(failed.value)
    assert ctx.deps.turn_markers.sampled_gene_ids == []


async def test_a_sample_the_site_answers_carries_every_asked_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = _serve(monkeypatch)

    sampled = await _sample(_ASKED)

    assert step.asked == [None, *[_ASKED] * 4]
    assert sampled.result.attributes == _ASKED
    assert sampled.result.dropped_attributes == []
