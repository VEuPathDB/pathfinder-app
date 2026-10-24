"""A stored column fit the site did not show, saved with no refusal status, is
refused when it loads, so its verdict never reads as a count of none."""

from __future__ import annotations

from datetime import UTC, datetime

import ormsgpack
import pytest
from assistant_core.conversation.serde import build_checkpoint_serde
from langgraph.checkpoint.serde.jsonplus import EXT_PYDANTIC_V2, _msgpack_enc
from pydantic import JsonValue, ValidationError

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.column_fit import UNREADABLE_COLUMN_FIT, ColumnFit
from pathfinder.domain.evidence import EvidenceCard, VerificationReview
from pathfinder.tests._support.column_fits import tm_fit


def _checked(fit: ColumnFit) -> StrategyDomainState:
    review = VerificationReview(column_fits=[fit])
    return StrategyDomainState(
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


def _saved_before_the_status(fit: dict[str, JsonValue]) -> None:
    for key in ("refused_status", "no_value"):
        fit.pop(key)
    fit.update({"shown": False, "fits": "not_shown", "counted_in": "genes"})


def _reloaded(dumped: dict[str, JsonValue]) -> StrategyDomainState:
    blob = ormsgpack.packb(
        ormsgpack.Ext(
            EXT_PYDANTIC_V2,
            _msgpack_enc(
                (
                    StrategyDomainState.__module__,
                    "StrategyDomainState",
                    dumped,
                    "model_validate_json",
                )
            ),
        )
    )
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)
    loaded = serde.loads_typed(("msgpack", blob))
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


def test_a_checkpoint_with_an_unreadable_fit_reloads_with_no_verdict() -> None:
    dumped = _checked(tm_fit(0, 0)).model_dump()
    for review in (
        dumped["verification_digest"]["review"],
        dumped["last_evidence_card"]["review"],
    ):
        _saved_before_the_status(review["column_fits"][0])

    loaded = _reloaded(dumped)

    assert (loaded.verification_digest, loaded.last_evidence_card) == (None, None)


def test_a_checkpoint_with_a_refused_fit_reloads_whole() -> None:
    state = _checked(tm_fit(0, 0).model_copy(update={"refused_status": 400}))

    loaded = _reloaded(state.model_dump())

    assert loaded.verification_digest == state.verification_digest
    assert loaded.last_evidence_card == state.last_evidence_card


def test_a_stored_verdict_invalid_for_another_reason_still_fails() -> None:
    dumped = _checked(tm_fit(0, 0)).model_dump()
    dumped["verification_digest"]["success"] = "not a verdict"

    with pytest.raises(ValidationError) as refused:
        StrategyDomainState.model_validate(dumped)

    assert [e["loc"] for e in refused.value.errors()] == [
        ("verification_digest", "success")
    ]
