"""A rating is one score per message, on the trace of the turn that wrote it."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from pathfinder.platform.langfuse import scores
from pathfinder.platform.langfuse.scores import RatingScore, record_rating

_MESSAGE = UUID("88888888-8888-8888-8888-888888888888")
_CONVERSATION = UUID("99999999-9999-9999-9999-999999999999")
_TRACE = "0af7651916cd43dd8448eb211c80319c"


class _ScoreSink:
    def __init__(self) -> None:
        self.scores: list[dict[str, Any]] = []

    def create_score(self, **kwargs: Any) -> None:
        self.scores.append(kwargs)


@pytest.fixture
def sink(monkeypatch: pytest.MonkeyPatch) -> _ScoreSink:
    recorded = _ScoreSink()
    monkeypatch.setattr(scores, "get_langfuse", lambda: recorded)
    return recorded


def _rating(rating: str | None, trace_id: str | None = _TRACE) -> RatingScore:
    return RatingScore.model_validate(
        {
            "message_id": _MESSAGE,
            "conversation_id": _CONVERSATION,
            "trace_id": trace_id,
            "rating": rating,
            "metadata": {"site_id": "plasmodb", "cost_usd": 0.0412},
        },
    )


@pytest.mark.parametrize(
    ("rating", "value", "comment"),
    [("like", 1, "like"), ("dislike", -1, "dislike"), (None, 0, "cleared")],
)
def test_a_rating_scores_the_turn_s_trace(
    sink: _ScoreSink, rating: str | None, value: int, comment: str
) -> None:
    record_rating(_rating(rating))

    assert sink.scores == [
        {
            "score_id": f"rating-{_MESSAGE}",
            "name": "rating",
            "value": value,
            "data_type": "NUMERIC",
            "comment": comment,
            "trace_id": _TRACE,
            "session_id": None,
            "metadata": {
                "message_id": str(_MESSAGE),
                "site_id": "plasmodb",
                "cost_usd": 0.0412,
            },
        }
    ]


def test_a_changed_rating_writes_the_same_score_again(sink: _ScoreSink) -> None:
    record_rating(_rating("like"))
    record_rating(_rating("dislike"))

    assert [(s["score_id"], s["value"]) for s in sink.scores] == [
        (f"rating-{_MESSAGE}", 1),
        (f"rating-{_MESSAGE}", -1),
    ]


def test_a_turn_with_no_trace_scores_its_session(sink: _ScoreSink) -> None:
    record_rating(_rating("like", trace_id=None))

    assert [(s["trace_id"], s["session_id"]) for s in sink.scores] == [
        (None, str(_CONVERSATION))
    ]


def test_without_langfuse_a_rating_is_dropped(
    sink: _ScoreSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scores, "get_langfuse", lambda: None)

    record_rating(_rating("like"))

    assert sink.scores == []
