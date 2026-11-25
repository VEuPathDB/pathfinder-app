from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue

from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.readings import count_readings
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from strategist.domain.strategy.questions import SlotQuestion
from strategist.domain.strategy.readings import Reading
from strategist.tests._support.recorded_counts import serve_counts, wire
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByText"
_PARAM = "text_expression"
_READINGS = {"kinase": 2104, "protein kinase": 1190}


def _deps(monkeypatch: pytest.MonkeyPatch, record_class: str | None) -> LeadDeps:
    serve_counts(monkeypatch, lambda _search, params: _READINGS[wire(params, _PARAM)])
    deps = lead_deps(pipeline_state(user_prompt="kinases"))
    deps.state.domain.operational_spec = OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="c_text",
                text="kinases",
                search_name=_SEARCH,
                record_class=record_class,
                resolved_params={
                    "text_fields": BoundValue(
                        value=StringValue(value="product"), source="default"
                    )
                },
            )
        ],
    )
    return deps


def _asked() -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question="Which text names the kinases?",
                recommended_value="kinase",
                criterion_id="c_text",
                param_name=_PARAM,
                readings=[Reading(label=value, value=value) for value in _READINGS],
            )
        ],
    )


def _measured(deps: LeadDeps) -> list[Measurement]:
    spec = deps.state.domain.operational_spec
    assert spec is not None
    return spec.criteria[0].measurements


async def test_a_reading_is_counted_under_the_class_of_its_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, "transcript")

    await count_readings(deps, _asked())

    assert [(m.reading, m.count) for m in _measured(deps)] == list(_READINGS.items())


async def test_a_reading_of_a_criterion_whose_class_is_unknown_is_not_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(monkeypatch, None)

    await count_readings(deps, _asked())

    assert _measured(deps) == []
