"""The rating body names a like or a dislike, and nothing else."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.transport.http.routers.conversations.ratings import (
    MessageRatingRequest,
)


@pytest.mark.parametrize("rating", ["like", "dislike"])
def test_a_like_and_a_dislike_are_accepted(rating: str) -> None:
    assert MessageRatingRequest.model_validate({"rating": rating}).rating == rating


def test_a_rating_outside_like_and_dislike_is_refused() -> None:
    with pytest.raises(ValidationError, match="literal_error"):
        MessageRatingRequest.model_validate({"rating": "neutral"})


def test_a_field_the_body_does_not_declare_is_refused() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MessageRatingRequest.model_validate({"rating": "like", "weight": 2})
