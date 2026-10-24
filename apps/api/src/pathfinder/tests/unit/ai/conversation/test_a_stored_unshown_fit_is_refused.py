"""A stored column fit the site did not show, saved with no refusal status, is
refused when it loads, so its verdict never reads as a count of none and the
conversation still continues."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, TypeAliasType, get_args, get_origin
from uuid import uuid4

import pytest
from assistant_core.conversation.serde import build_checkpoint_serde
from pydantic import BaseModel, JsonValue, ValidationError, WrapValidator

from pathfinder.ai.graph.rebuild import rebuilt_state
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.column_fit import UNREADABLE_COLUMN_FIT, ColumnFit
from pathfinder.domain.evidence import EvidenceCard, VerificationReview
from pathfinder.tests._support.column_fits import tm_fit


def _checked(fit: ColumnFit) -> StrategyDomainState:
    review = VerificationReview(column_fits=[fit])
    state = StrategyDomainState(
        verification_digest=VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="p",
            reason="r",
            success=True,
            review=review,
        ),
        last_evidence_card=EvidenceCard(
            check_id="call_verify",
            revision="rev-1",
            site_id="plasmodb",
            checked_at=datetime(2026, 10, 24, 9, 30, tzinfo=UTC),
            site_read="read",
            steps=[],
            controls=[],
            citations=[],
            review=review,
        ),
    )
    state.turn_markers.record_column_fits([fit])
    return state


def _saved_before_the_status(fit: dict[str, JsonValue]) -> None:
    for key in ("refused_status", "no_value"):
        fit.pop(key)
    fit.update({"shown": False, "fits": "not_shown", "counted_in": "genes"})


def _old_fits(dumped: dict[str, Any]) -> list[dict[str, JsonValue]]:
    return [
        dumped["verification_digest"]["review"]["column_fits"][0],
        dumped["last_evidence_card"]["review"]["column_fits"][0],
        dumped["turn_markers"]["column_fits"][0],
    ]


def _reloaded(dumped: dict[str, Any]) -> StrategyDomainState:
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)
    saved = serde.dumps_typed(StrategyDomainState.model_construct(**dumped))
    loaded = serde.loads_typed(saved)
    assert type(loaded) is StrategyDomainState
    return loaded


def test_a_stored_fit_with_no_refusal_status_is_refused_by_type() -> None:
    stored = tm_fit(0, 0).model_dump(by_alias=True, mode="json")
    del stored["refusedStatus"]
    stored["shown"] = False

    with pytest.raises(ValidationError) as refused:
        ColumnFit.model_validate(stored)

    assert [e["type"] for e in refused.value.errors()] == [UNREADABLE_COLUMN_FIT]


def test_a_stored_refusal_reloads_with_its_status() -> None:
    fit = tm_fit(0, 0).model_copy(update={"refused_status": 400})

    back = ColumnFit.model_validate(fit.model_dump(by_alias=True, mode="json"))

    assert (back, back.fits) == (fit, "not_shown")


def test_a_checkpoint_with_unreadable_fits_reloads_and_its_next_turn_runs() -> None:
    dumped = _checked(tm_fit(0, 0)).model_dump()
    for fit in _old_fits(dumped):
        _saved_before_the_status(fit)

    loaded = _reloaded(dumped)
    state = rebuilt_state(
        PipelineState(
            conversation_id=uuid4(),
            user_id=uuid4(),
            site_id="plasmodb",
            mode="strategy",
            domain=loaded,
        )
    )
    markers = state.domain.markers_for(uuid4())
    markers.record_column_fits([tm_fit(40, 40)])

    assert (
        loaded.verification_digest,
        loaded.last_evidence_card,
        loaded.turn_markers.column_fits,
    ) == (None, None, [])
    assert [f.fits for f in state.domain.turn_markers.column_fits] == ["all"]


def test_a_checkpoint_with_a_refused_fit_reloads_whole() -> None:
    state = _checked(tm_fit(0, 0).model_copy(update={"refused_status": 400}))

    loaded = _reloaded(state.model_dump())

    assert loaded.verification_digest == state.verification_digest
    assert loaded.last_evidence_card == state.last_evidence_card
    assert loaded.turn_markers.column_fits == state.turn_markers.column_fits


def test_a_stored_verdict_invalid_for_another_reason_still_fails() -> None:
    dumped = _checked(tm_fit(0, 0)).model_dump()
    dumped["verification_digest"]["success"] = "not a verdict"

    with pytest.raises(ValidationError) as refused:
        StrategyDomainState.model_validate(dumped)

    assert [e["loc"] for e in refused.value.errors()] == [
        ("verification_digest", "success")
    ]


def test_an_unreadable_fit_beside_another_error_still_fails() -> None:
    dumped = _checked(tm_fit(0, 0)).model_dump()
    _saved_before_the_status(_old_fits(dumped)[0])
    dumped["verification_digest"]["success"] = "not a verdict"

    with pytest.raises(ValidationError) as refused:
        StrategyDomainState.model_validate(dumped)

    assert sorted(e["type"] for e in refused.value.errors()) == [
        "bool_parsing",
        UNREADABLE_COLUMN_FIT,
    ]


def _wraps(metadata: tuple[object, ...]) -> bool:
    return any(isinstance(m, WrapValidator) for m in metadata)


def _parts(annotation: object) -> tuple[tuple[object, ...], bool]:
    origin = get_origin(annotation)
    if isinstance(annotation, TypeAliasType):
        return (annotation.__value__,), False
    if isinstance(origin, TypeAliasType):
        value = origin.__value__
        wraps = get_origin(value) is Annotated and _wraps(get_args(value)[1:])
        return get_args(annotation), wraps
    if origin is Annotated:
        inner, *metadata = get_args(annotation)
        return (inner,), _wraps(tuple(metadata))
    return get_args(annotation), False


def _unwrapped(
    annotation: object, path: str, wrapped: bool, seen: tuple[type, ...]
) -> list[str]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation is ColumnFit:
            return [] if wrapped else [path]
        if annotation in seen:
            return []
        return [
            p
            for name, field in annotation.model_fields.items()
            for p in _unwrapped(
                field.annotation, f"{path}.{name}", wrapped, (*seen, annotation)
            )
        ]
    inner, wraps = _parts(annotation)
    return [p for a in inner for p in _unwrapped(a, path, wrapped or wraps, seen)]


def test_every_column_fit_a_conversation_keeps_is_refused_when_unreadable() -> None:
    assert _unwrapped(PipelineState, "PipelineState", False, ()) == []
