"""The Lead counts one catalog search's records by each value of a column: the
turn keeps the counts as a fact, the thread gets a table, and a column the site
cannot count comes back to the model with the columns it can."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.toolsets import FunctionToolset, WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import SearchMatch

from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.tools.standalone import column_tally, search_reads
from pathfinder.ai.tools.standalone.column_tally import count_by_column
from pathfinder.services.experiment.column_tally import (
    ColumnTally,
    ColumnTallyRefusedError,
    TallyOnly,
)
from pathfinder.services.experiment.tally_rows import TallyRow
from pathfinder.services.experiment.variant_comparison import VariantInput, VariantSpec
from pathfinder.tests._support.run_context import lead_run_context

_SEARCH = VariantInput(label="datasets", search_name="AllDatasets", parameters={})
_SPEC = VariantSpec(
    label="datasets", search_name="AllDatasets", record_type="dataset", parameters={}
)
_TALLY = ColumnTally(
    id="tally_0a1b2c3d",
    title="Datasets by Organism(s), where Category is RNASeq",
    search_name="AllDatasets",
    record_type="dataset",
    record_noun="dataset",
    column="organism_prefix",
    column_label="Organism(s)",
    only=TallyOnly(column="newcategory", values=["RNASeq"]),
    only_label="Category",
    total=379,
    distinct=58,
    rows=[
        TallyRow(value="Anopheles gambiae PEST", count=40),
        TallyRow(value="Anopheles coluzzii AcolN3", count=11),
    ],
    site_id="vectorbase",
)


class _Ran:
    def __init__(self) -> None:
        self.asked: list[tuple[str, TallyOnly | None, str]] = []

    async def __call__(
        self,
        site_id: str,
        spec: VariantSpec,
        column: str,
        only: TallyOnly | None,
        *,
        record_noun: str,
    ) -> ColumnTally:
        del site_id, spec
        self.asked.append((column, only, record_noun))
        if column == "overview":
            msg = "dataset records cannot be counted by overview."
            raise ColumnTallyRefusedError(msg)
        return _TALLY


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    async def resolved(
        _ctx: object, _search: VariantInput, *, record_type: str, framing: bool
    ) -> VariantSpec:
        assert (record_type, framing) == ("dataset", True)
        return _SPEC

    fake = _Ran()
    monkeypatch.setattr(column_tally, "resolved_search", resolved)
    monkeypatch.setattr(column_tally, "run_column_tally", fake)
    return fake


async def test_the_counts_are_kept_as_a_fact_and_drawn_as_a_table(ran: _Ran) -> None:
    ctx = lead_run_context(site_id="vectorbase")

    result = await count_by_column(
        ctx,
        _SEARCH,
        record_type="dataset",
        column="organism_prefix",
        only_column="newcategory",
        only_values=["RNASeq"],
    )

    assert ran.asked == [
        (
            "organism_prefix",
            TallyOnly(column="newcategory", values=["RNASeq"]),
            "dataset",
        )
    ]
    assert ctx.deps.state.turn_markers.tallies == [_TALLY.fact()]
    chunks = [
        c
        for c in result.metadata or []
        if isinstance(c, DataChunk) and c.type == "data-column-tally"
    ]
    assert [c.data for c in chunks] == [_TALLY.model_dump(by_alias=True, mode="json")]


async def test_a_column_the_site_cannot_count_is_returned_to_the_model(
    ran: _Ran,
) -> None:
    with pytest.raises(ModelRetry, match="cannot be counted by overview"):
        await count_by_column(
            lead_run_context(), _SEARCH, record_type="dataset", column="overview"
        )

    assert ran.asked == [("overview", None, "dataset")]


async def test_a_filter_names_its_column_and_its_values_together(ran: _Ran) -> None:
    with pytest.raises(ModelRetry, match="only_column and only_values"):
        await count_by_column(
            lead_run_context(),
            _SEARCH,
            record_type="dataset",
            column="organism_prefix",
            only_column="newcategory",
        )

    assert ran.asked == []


async def test_an_unlisted_search_is_looked_up_under_the_record_type_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    looked_under: list[str | list[str] | None] = []

    async def unlisted(_site_id: str, _names: list[str]) -> dict[str, str]:
        return {}

    async def lookup(
        _site_id: str,
        record_type: str | list[str] | None,
        _query: str,
        **_: object,
    ) -> list[SearchMatch]:
        looked_under.append(record_type)
        return [
            SearchMatch(
                name="AllDatasets",
                display_name="Datasets",
                description="",
                record_type="dataset",
            )
        ]

    monkeypatch.setattr(search_reads, "search_record_types", unlisted)
    monkeypatch.setattr(catalog, "search_for_searches", lookup)
    named = VariantInput(
        label="datasets", search_name="RNA-Seq datasets", parameters={}
    )

    with pytest.raises(ModelRetry, match=r"finds: AllDatasets \(Datasets\)"):
        await count_by_column(
            lead_run_context(site_id="vectorbase"),
            named,
            record_type="dataset",
            column="organism_prefix",
        )

    assert looked_under == ["dataset"]


def test_each_way_the_count_is_refused_keeps_a_retry() -> None:
    read_once = build_lead_toolset()
    assert isinstance(read_once, WrapperToolset)
    refusal_memory = read_once.wrapped
    assert isinstance(refusal_memory, WrapperToolset)
    base = refusal_memory.wrapped
    assert isinstance(base, FunctionToolset)

    assert base.tools["count_by_column"].max_retries == 6
