from __future__ import annotations

import inspect
import json
import types
from collections.abc import Callable, Iterator
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from strategist.ai.graph.state import VerificationDigest
from strategist.ai.lead import deltas
from strategist.ai.lead.deltas import EditDelta, FrameResult, RecoveryDelta
from strategist.ai.lead.edit_dispatch import edit_strategy
from strategist.ai.lead.frame_dispatch import frame_problem
from strategist.ai.lead.sub_agent_dispatch import build_strategy, recover_failed_steps
from strategist.ai.lead.verify_dispatch import verify_strategy
from strategist.domain.pending_plan import PendingPlan

_DISPATCHES: list[Callable[..., Any]] = [
    frame_problem,
    edit_strategy,
    build_strategy,
    recover_failed_steps,
    verify_strategy,
]


def _models(annotation: object) -> Iterator[type[BaseModel]]:
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        yield annotation
        return
    if get_origin(annotation) in (Union, types.UnionType) or get_args(annotation):
        for arg in get_args(annotation):
            yield from _models(arg)


def _read_by_the_lead() -> set[type[BaseModel]]:
    roots = {
        model
        for _, model in inspect.getmembers(deltas, inspect.isclass)
        if issubclass(model, BaseModel) and model.__module__ == deltas.__name__
    }
    for dispatch in _DISPATCHES:
        roots |= set(_models(get_type_hints(dispatch)["return"]))
    seen: set[type[BaseModel]] = set()
    pending = list(roots)
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for field in model.model_fields.values():
            pending.extend(_models(field.annotation))
    return seen


def _free_summaries(models: set[type[BaseModel]]) -> list[str]:
    return sorted(
        model.__name__
        for model in models
        if "summary" in model.model_fields
        and model.model_fields["summary"].annotation is str
    )


def test_no_result_the_lead_reads_stores_a_free_summary() -> None:
    models = _read_by_the_lead()

    assert {FrameResult, EditDelta} <= models
    assert _free_summaries(models) == []


def test_a_planted_free_summary_is_found() -> None:
    class Planted(BaseModel):
        summary: str = ""

    assert _free_summaries({Planted}) == ["Planted"]


def test_a_sub_agents_prose_reaches_the_lead_only_as_a_pending_plan() -> None:
    edit_plan = EditDelta.model_fields["pending_plan"].annotation
    frame_plan = FrameResult.model_computed_fields["pending_plan"].return_type

    assert (edit_plan, frame_plan, FrameResult.model_fields["notes"].exclude) == (
        PendingPlan | None,
        PendingPlan | None,
        True,
    )


_SUB_AGENT_OUTPUTS: list[type[BaseModel]] = [
    FrameResult,
    RecoveryDelta,
    VerificationDigest,
]

_FREE_TEXT_THE_LEAD_READS = {
    ("RecoveryDelta", "actionsTaken"): (
        "what recovery says it did; the outcome the Lead reports is re-read from "
        "the site after it"
    ),
    ("VerificationDigest", "prose"): (
        "what the records VERIFY read look like; the verdict, checks and gaps "
        "are computed"
    ),
    ("VerificationDigest", "keyFindings"): (
        "observations beside the computed checks, never the verdict"
    ),
    ("VerificationDigest", "noteRefs"): "the ids of notes VERIFY wrote",
}


def _free_text(model: type[BaseModel]) -> set[tuple[str, str]]:
    written = model.model_json_schema(mode="validation").get("properties", {})
    read = model.model_json_schema(mode="serialization").get("properties", {})
    return {
        (model.__name__, name)
        for name, field in written.items()
        if name in read and _a_string(field)
    }


def _a_string(field: dict[str, Any]) -> bool:
    text = json.dumps(field)
    return '"type": "string"' in text and "enum" not in text and "$ref" not in text


def test_every_free_text_a_sub_agent_writes_and_the_lead_reads_is_listed() -> None:
    found = {key for model in _SUB_AGENT_OUTPUTS for key in _free_text(model)}

    assert found == set(_FREE_TEXT_THE_LEAD_READS)
