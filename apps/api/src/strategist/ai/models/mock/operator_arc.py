from __future__ import annotations

from dataclasses import replace

from assistant_core.models.scripted import deferred_tool_resolved, next_unmade_call
from pydantic_ai.messages import ModelMessage, ToolCallPart
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import (
    ChoiceAnswer,
    ChoiceProbability,
    DecisionRequest,
    DecisionResponse,
)

from strategist.ai.lead.intent import IntentClassification
from strategist.ai.models.mock.arc_readings import read_as, stated
from strategist.ai.models.mock.consult_arc import (
    CONSULT,
    frame_and_ask,
    since_the_answer,
)
from strategist.ai.models.mock.lead_flow import built_journey
from strategist.ai.models.mock.site_values import SiteValues
from strategist.ai.models.mock.specs import SpecPlan, combine, leaf
from strategist.ai.models.mock.strategy_specs import (
    TM_RANGE,
    signal_peptide,
    tm_domains,
)
from strategist.domain.strategy.operator_reading import OPERATOR_QUESTION

SIGNAL_PEPTIDE = "a predicted signal peptide"
TM_DOMAINS = "2 to 99 transmembrane domains"
TM_BOUNDS = (
    (f"at least {TM_RANGE[0]} transmembrane domains", ">=", int(TM_RANGE[0])),
    (f"at most {TM_RANGE[1]} transmembrane domains", "<=", int(TM_RANGE[1])),
)
_READ = "intersect"
_READ_CONFIDENCE = 0.93

operator_reading = read_as(
    IntentClassification.NEW_STRATEGY,
    stated(
        "property",
        "signal peptide",
        SIGNAL_PEPTIDE,
        typed={"kind": "property", "phrase": SIGNAL_PEPTIDE},
    ),
    *(
        stated(
            "count",
            "transmembrane domains",
            value,
            typed={
                "kind": "count",
                "feature": "transmembrane domains",
                "op": op,
                "value": bound,
            },
            quote=TM_DOMAINS,
        )
        for value, op, bound in TM_BOUNDS
    ),
)


def union_of_the_stated(values: SiteValues) -> SpecPlan:
    left = signal_peptide(values)
    right = tm_domains(values, *TM_RANGE)
    left = replace(left, answers=(*left.answers, SIGNAL_PEPTIDE))
    right = replace(
        right, answers=(*right.answers, *(value for value, _, _ in TM_BOUNDS))
    )
    return SpecPlan(
        title=f"{values.organism} signal peptide or membrane genes (mock)",
        criteria=(left, right),
        structure=combine(CombineOp.UNION, leaf(left), leaf(right)),
    )


async def read_as_intersect(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return DecisionResponse(
        answers=[
            ChoiceAnswer(
                type="choice",
                name=OPERATOR_QUESTION,
                choice=_READ,
                probabilities=[
                    ChoiceProbability(value=_READ, probability=_READ_CONFIDENCE),
                    ChoiceProbability(value="union", probability=0.05),
                    ChoiceProbability(value="not_stated", probability=0.02),
                ],
                confidence=_READ_CONFIDENCE,
            )
        ]
    )


def operator_card(messages: list[ModelMessage]) -> ToolCallPart:
    if not deferred_tool_resolved(messages, CONSULT):
        return next_unmade_call(frame_and_ask(messages), messages)
    return next_unmade_call(built_journey(messages), since_the_answer(messages))
