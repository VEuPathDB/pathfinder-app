from __future__ import annotations

from typing import Annotated, TypeAliasType, get_args, get_origin

import annotated_types
import pytest
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    PlainValidator,
    WrapValidator,
)

from pathfinder.ai.graph.state import clipped_draft
from pathfinder.ai.lead.deltas import FrameResult, VerificationDelta
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.domain import clipped
from pathfinder.domain.omitted_from_input import OmittedFromInput

_NORMALIZERS = {
    "_one_option_is_a_free_text_question",
    "_keys_on_the_readings_are_the_question_s",
    "_a_search_and_a_site_only_where_the_problem_takes_them",
}
_LIMITS = (
    annotated_types.MaxLen,
    annotated_types.Ge,
    annotated_types.Gt,
    annotated_types.Le,
    annotated_types.Lt,
)
_FUNCTIONAL = (AfterValidator, BeforeValidator, PlainValidator, WrapValidator)


def _normalized_before(metadata: tuple[object, ...]) -> bool:
    return any(
        isinstance(m, BeforeValidator) and m.func is clipped_draft for m in metadata
    )


def _normalizes(
    validator: AfterValidator | BeforeValidator | PlainValidator | WrapValidator,
) -> bool:
    func = validator.func
    return func is clipped_draft or func.__module__ == clipped.__name__


def _rules(metadata: list[object]) -> list[str]:
    return [
        *(str(m) for m in metadata if isinstance(m, _LIMITS)),
        *(
            f"{type(m).__name__}({m.func.__qualname__})"
            for m in metadata
            if isinstance(m, _FUNCTIONAL) and not _normalizes(m)
        ),
    ]


def _walk(annotation: object, found: dict[type[BaseModel], list[str]]) -> None:
    if isinstance(annotation, TypeAliasType):
        _walk(annotation.__value__, found)
        return
    if get_origin(annotation) is Annotated:
        inner, *metadata = get_args(annotation)
        rules = _rules(metadata)
        if rules:
            found.setdefault(BaseModel, []).extend(rules)
        if not _normalized_before(tuple(metadata)):
            _walk(inner, found)
        return
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in found:
            return
        decorators = annotation.__pydantic_decorators__
        found[annotation] = [
            *(n for n in decorators.model_validators if n not in _NORMALIZERS),
            *(n for n in decorators.field_validators if n not in _NORMALIZERS),
        ]
        for name, field in annotation.model_fields.items():
            if OmittedFromInput in field.metadata:
                continue
            found[annotation].extend(
                f"{name}: {rule}" for rule in _rules(field.metadata)
            )
            _walk(field.annotation, found)
        return
    for argument in get_args(annotation):
        _walk(argument, found)


def _judged(output: type[BaseModel]) -> dict[str, list[str]]:
    found: dict[type[BaseModel], list[str]] = {}
    _walk(output, found)
    return {model.__name__: rules for model, rules in found.items() if rules}


@pytest.mark.parametrize("output", [FrameResult, VerificationDelta, LeadResponse])
def test_no_output_type_judges_or_limits_what_the_model_writes(
    output: type[BaseModel],
) -> None:
    assert _judged(output) == {}


def _refuse_empty(value: str) -> str:
    if not value:
        raise ValueError(value)
    return value


class _Item(BaseModel):
    value: Annotated[str, AfterValidator(_refuse_empty)]


class _Judging(BaseModel):
    note: Annotated[str, clipped.text_clipped_to(10)]
    first: Annotated[str, BeforeValidator(_refuse_empty)]
    items: list[_Item]


def test_a_judgement_in_field_metadata_is_found_and_a_clip_is_not() -> None:
    assert _judged(_Judging) == {
        "_Judging": ["first: BeforeValidator(_refuse_empty)"],
        "_Item": ["value: AfterValidator(_refuse_empty)"],
    }


_QUESTION = {
    "question": "How many genomes?",
    "dimension": "other",
    "recommendedValue": "At most 5",
    "criterionId": "c_families",
    "paramName": "phyletic_expression",
}
_READING = {"label": "At most 3 genomes", "value": "MICR>=1T AND MICR<=3T"}


def _framed(**fields: object) -> dict[str, object]:
    return {"disposition": "needs_user", "summary": "s"} | fields


def _digest(**fields: object) -> dict[str, object]:
    return {
        "digest": {
            "disposition": "done",
            "prose": "Checked.",
            "reason": "r",
            "success": True,
        }
        | fields
    }


def _row(**fields: object) -> dict[str, object]:
    return {"text": "kinases", "turn": 1, "how": "search", "status": "met"} | fields


def _gene(gene_id: str) -> dict[str, object]:
    return {"geneId": gene_id, "fits": "yes", "why": "w"}


_JUDGEMENTS: list[tuple[type[BaseModel], dict[str, object]]] = [
    (
        FrameResult,
        _framed(
            requirementProblems=[
                {
                    "requirement": "R1",
                    "problem": "request_leaves_it_open",
                    "search": "S",
                }
            ]
        ),
    ),
    (
        FrameResult,
        _framed(
            requirementProblems=[
                {"requirement": "R1", "problem": "another_site_answers"}
            ]
        ),
    ),
    (FrameResult, _framed(openQuestions=[_QUESTION | {"readings": [_READING]}])),
    (
        FrameResult,
        _framed(
            openQuestions=[
                _QUESTION | {"readings": [_READING] * 4, "options": ["a", "b"]}
            ]
        ),
    ),
    (
        FrameResult,
        _framed(
            openQuestions=[_QUESTION | {"readings": [_READING | {"label": "x" * 200}]}]
        ),
    ),
    (FrameResult, _framed(openQuestions=[{"question": "Which?", "options": ["only"]}])),
    (FrameResult, _framed(openQuestions=[{"question": "q" * 400}])),
    (VerificationDelta, _digest(reason="r" * 300, prose="p" * 5000)),
    (VerificationDelta, _digest(keyFindings=["k"] * 11, noteRefs=["n"] * 11)),
    (
        VerificationDelta,
        _digest(
            remember=[{"name": "n" * 250, "summary": "s" * 500, "tags": ["t"] * 9}] * 6
        ),
    ),
    (VerificationDelta, _digest(review={"requirements": [_row()]})),
    (
        VerificationDelta,
        _digest(review={"requirements": [_row(status="unmet", answeredBy=["c1"])]}),
    ),
    (
        VerificationDelta,
        _digest(review={"requirements": [_row(turn=0, answeredBy=["c"] * 9)] * 21}),
    ),
    (
        VerificationDelta,
        _digest(
            review={"sources": [{"kind": "web", "label": "l" * 300, "why": "w"}] * 11}
        ),
    ),
    (
        VerificationDelta,
        _digest(review={"sampledGenes": [_gene(f"PF3D7_{n}") for n in range(9)]}),
    ),
    (
        VerificationDelta,
        _digest(
            review={
                "columnFits": [
                    {
                        "criterionId": "c1",
                        "criterionText": "t",
                        "wdkStepId": 1,
                        "column": "c",
                        "displayName": "d",
                        "boundValue": "1",
                        "total": 1,
                        "fitting": 5,
                        "fittingAtMost": -1,
                    }
                ]
            }
        ),
    ),
    (LeadResponse, {"prose": "p" * 5000, "strategyChanged": False}),
    (
        LeadResponse,
        {
            "prose": "p",
            "strategyChanged": False,
            "askedQuestions": [{"question": "q", "options": ["only"]}] * 9,
        },
    ),
]


@pytest.mark.parametrize(("output", "payload"), _JUDGEMENTS)
def test_an_answer_that_breaks_only_a_judgement_validates(
    output: type[BaseModel], payload: dict[str, object]
) -> None:
    output.model_validate(payload)
