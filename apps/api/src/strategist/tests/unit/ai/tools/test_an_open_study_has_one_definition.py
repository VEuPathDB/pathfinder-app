"""Every EDA tool refuses a thread with no study open, and a dataset id the
catalog lacks, with one sentence each, written in one place."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.tools.standalone import (
    _eda_open,
    eda_analysis,
    eda_catalog,
    eda_cut,
    eda_statistics,
    eda_step,
)
from strategist.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from strategist.services.eda.catalog import UnknownEdaDatasetError
from strategist.tests._support.run_context import lead_run_context

_STANDALONE = Path(_eda_open.__file__).parent
_VARIABLE = EdaVariableSpecIn(entity_id="EUPATH_0000609", variable_id="EUPATH_0000704")

type _Call = Callable[[RunContext[LeadDeps]], Awaitable[Any]]

_NEEDS_A_STUDY: dict[str, _Call] = {
    "set_eda_filters": lambda ctx: eda_analysis.set_eda_filters(ctx, dataset_id="DS_1"),
    "preview_eda_subset": lambda ctx: eda_analysis.preview_eda_subset(
        ctx, entity_id="EUPATH_0000609"
    ),
    "ask_eda_cut": lambda ctx: eda_cut.ask_eda_cut(ctx, variable_id="EUPATH_0000704"),
    "read_eda_statistics": lambda ctx: eda_statistics.read_eda_statistics(
        ctx,
        kind="contingency",
        x_variable=_VARIABLE,
        y_variable=_VARIABLE,
        output_entity_id="EUPATH_0000609",
    ),
    "create_eda_step": eda_step.create_eda_step,
}


@pytest.mark.parametrize("tool", sorted(_NEEDS_A_STUDY))
async def test_a_tool_on_a_thread_with_no_study_open_is_refused_with_the_one_sentence(
    monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    async def unbound(*, conversation_id: object) -> None:
        del conversation_id

    monkeypatch.setattr(_eda_open, "bound_conversation_analysis", unbound)

    with pytest.raises(ModelRetry) as refused:
        await _NEEDS_A_STUDY[tool](lead_run_context())

    assert str(refused.value) == _eda_open.NO_STUDY_OPEN


_READS_A_DATASET: dict[str, _Call] = {
    "open_eda_analysis": lambda ctx: eda_analysis.open_eda_analysis(
        ctx, dataset_id="DS_unknown", purpose="read it"
    ),
    "describe_eda_study": lambda ctx: eda_catalog.describe_eda_study(
        ctx, dataset_id="DS_unknown"
    ),
}


@pytest.mark.parametrize("tool", sorted(_READS_A_DATASET))
async def test_a_dataset_the_catalog_lacks_is_refused_with_the_one_sentence(
    monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    async def unknown(site_id: str, dataset_id: str) -> None:
        raise UnknownEdaDatasetError(dataset_id, ["DS_1", "DS_2"])

    monkeypatch.setattr(_eda_open, "get_study_detail_for_dataset", unknown)
    error = UnknownEdaDatasetError("DS_unknown", ["DS_1", "DS_2"])

    with pytest.raises(ModelRetry) as refused:
        await _READS_A_DATASET[tool](lead_run_context())

    assert str(refused.value) == f"{error.guidance} {_eda_open.FIND_A_DATASET}"


@pytest.mark.parametrize("words", ["no study open", "find a real dataset id"])
def test_each_sentence_is_written_in_one_module(words: str) -> None:
    holding = sorted(
        path.name
        for path in _STANDALONE.glob("*.py")
        if words in path.read_text().replace("\n", " ")
    )

    assert holding == ["_eda_open.py"]
