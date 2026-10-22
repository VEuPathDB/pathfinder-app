from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.readings import count_readings
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SEARCH = "GenesByText"
_PARAM = "text_expression"
_READINGS = {"kinase": 2104, "protein kinase": 1190}


def _deps(record_class: str | None) -> LeadDeps:
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
    for value, count in _READINGS.items():
        deps.turn_counts.remember(
            "plasmodb",
            "transcript",
            _SEARCH,
            {
                "text_fields": StringValue(value="product"),
                _PARAM: StringValue(value=value),
            },
            count,
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


async def test_a_reading_is_counted_under_the_class_of_its_criterion() -> None:
    deps = _deps("transcript")

    await count_readings(deps, _asked())

    assert [(m.reading, m.count) for m in _measured(deps)] == list(_READINGS.items())


async def test_a_reading_of_a_criterion_whose_class_is_unknown_is_not_counted() -> None:
    deps = _deps(None)

    await count_readings(deps, _asked())

    assert _measured(deps) == []
