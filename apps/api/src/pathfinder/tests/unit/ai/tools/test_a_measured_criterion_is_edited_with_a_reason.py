"""A value edit on a criterion the controls chose states why, because the counts
the controls measured belong to the values they measured."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.step_rationale import ControlsRationale
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    PARAMS,
    WORDS,
    choose,
    read,
    serve_site,
)

_MEASURED = ControlsRationale(
    task_id="0c6100d2-0000-4000-8000-000000000001",
    search_name=EXPORTED.name,
    source="catalog",
    basis="the site's catalog",
    informs="recovering",
    recovered=20,
    positives=80,
    admitted=0,
    negatives=40,
    result_size=191,
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_site(monkeypatch)


@pytest.mark.asyncio
async def test_the_counts_do_not_outlive_the_values_they_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(
            criteria=[
                Criterion(
                    id="c_gpi",
                    text=WORDS,
                    search_name=EXPORTED.name,
                    rationale=_MEASURED,
                )
            ]
        )
    )

    await read(monkeypatch, state, EXPORTED)

    with pytest.raises(ModelRetry) as refused:
        await choose(
            state, None, params=PARAMS | {"organism": ["Plasmodium vivax P01"]}
        )

    assert str(refused.value) == (
        "c_gpi binds GenesByExportPrediction with no why. Pass why with a basis "
        "(parameter, organism, record_type, only_match or nearest), the term that "
        "decides it, and one line of reason of at most 160 characters holding the "
        "term. The catalog answered 2 searches for it, first Exported Protein 0.44, "
        "Gene Text Search. Nothing was recorded."
    )

    assert state.operational_spec_draft.criteria[0].rationale == _MEASURED
