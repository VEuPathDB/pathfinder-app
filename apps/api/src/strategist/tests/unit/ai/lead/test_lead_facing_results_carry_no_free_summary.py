from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Iterator
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from strategist.ai.lead import deltas
from strategist.ai.lead.deltas import EditDelta, FrameResult
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
