"""What a rating of one message does to the cases that message wrote."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistant_core.memory.schemas import MemoryValue

from pathfinder.domain.message_rating import (
    PINNED_TAG,
    StandingRating,
    partition_cases,
    pinned,
    settle_cases,
    unpinned,
)

CREATED = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _value(kind: str = "case", *, tags: list[str] | None = None) -> MemoryValue:
    return MemoryValue(
        kind=kind,
        name="kinases",
        summary="find every kinase in P. falciparum: 142",
        tags=["plasmodb", *(tags or [])],
        site_id="plasmodb",
        content={"goal": "find every kinase in P. falciparum", "root_count": 142},
        created_at=CREATED,
    )


def _other(rating: str, *keys: str, minutes: int = 0) -> StandingRating:
    return StandingRating.model_validate(
        {
            "rating": rating,
            "case_keys": list(keys),
            "updated_at": CREATED + timedelta(minutes=minutes),
        }
    )


def test_a_case_whose_key_stands_disliked_is_withheld() -> None:
    case = (_value(), "case:abc")
    note = (_value("gene_set_note"), "case:abc")

    parts = partition_cases(
        [case, note], own=None, others=[_other("dislike", "case:abc")]
    )

    assert parts.withheld == [case]
    assert parts.written == [note]


def test_a_case_of_a_disliked_message_is_withheld() -> None:
    case = (_value(), "case:abc")

    parts = partition_cases([case], own="dislike", others=[])

    assert parts.withheld == [case]
    assert parts.written == []


def test_a_liked_case_is_written_pinned_once() -> None:
    fresh = (_value(), "case:abc")
    already = (_value(tags=[PINNED_TAG]), "case:def")

    parts = partition_cases([fresh, already], own="like", others=[])

    written_tags = [value.tags for value, _key in parts.written]
    assert written_tags == [["plasmodb", "pinned"], ["plasmodb", "pinned"]]
    assert parts.withheld == []


def test_an_unrated_case_is_written_as_it_is() -> None:
    case = (_value(), "case:abc")

    parts = partition_cases([case], own=None, others=[_other("like", "case:xyz")])

    assert parts.written == [case]


def test_the_own_rating_decides_before_another_message() -> None:
    case = (_value(), "case:abc")

    parts = partition_cases(
        [case], own="like", others=[_other("dislike", "case:abc", minutes=5)]
    )

    assert [key for _value, key in parts.written] == ["case:abc"]
    assert PINNED_TAG in parts.written[0][0].tags


def test_between_two_other_messages_the_latest_decides() -> None:
    case = (_value(), "case:abc")
    older_like = _other("like", "case:abc", minutes=1)
    newer_dislike = _other("dislike", "case:abc", minutes=2)

    disliked = partition_cases([case], own=None, others=[older_like, newer_dislike])
    liked = partition_cases(
        [case],
        own=None,
        others=[
            _other("dislike", "case:abc", minutes=1),
            _other("like", "case:abc", minutes=2),
        ],
    )

    assert disliked.withheld == [case]
    assert [value.tags for value, _key in liked.written] == [["plasmodb", "pinned"]]


def test_unpinning_a_pinned_value_gives_the_value_back() -> None:
    value = _value()

    assert unpinned(pinned(value)) == value
    assert pinned(pinned(value)).tags == ["plasmodb", "pinned"]


def test_a_dislike_takes_a_stored_case_out_and_keeps_its_value() -> None:
    value = _value()

    moves = settle_cases(
        case_keys=["case:abc"],
        stored={"case:abc": value},
        withheld={},
        own="dislike",
        others=[],
    )

    assert moves.remove == ["case:abc"]
    assert moves.put == []
    assert moves.withheld == {"case:abc": value}


def test_a_like_puts_a_withheld_case_back_pinned() -> None:
    value = _value()

    moves = settle_cases(
        case_keys=["case:abc"],
        stored={},
        withheld={"case:abc": value},
        own="like",
        others=[],
    )

    assert moves.put == [(pinned(value), "case:abc")]
    assert moves.remove == []
    assert moves.withheld == {}


def test_a_clear_puts_a_case_back_unpinned() -> None:
    value = _value()

    from_withheld = settle_cases(
        case_keys=["case:abc"],
        stored={},
        withheld={"case:abc": value},
        own=None,
        others=[],
    )
    from_pinned = settle_cases(
        case_keys=["case:abc"],
        stored={"case:abc": pinned(value)},
        withheld={},
        own=None,
        others=[],
    )

    assert from_withheld.put == [(value, "case:abc")]
    assert from_pinned.put == [(value, "case:abc")]


def test_a_clear_under_another_message_s_dislike_keeps_the_case_out() -> None:
    value = _value()

    moves = settle_cases(
        case_keys=["case:abc"],
        stored={},
        withheld={"case:abc": value},
        own=None,
        others=[_other("dislike", "case:abc")],
    )

    assert moves.put == []
    assert moves.withheld == {"case:abc": value}


def test_a_case_the_researcher_deleted_is_not_written_back() -> None:
    moves = settle_cases(
        case_keys=["case:abc"],
        stored={},
        withheld={},
        own="like",
        others=[],
    )

    assert moves.put == []
    assert moves.remove == []


def test_a_stored_case_already_in_its_rated_shape_is_not_written_again() -> None:
    value = _value()

    moves = settle_cases(
        case_keys=["case:abc"],
        stored={"case:abc": pinned(value)},
        withheld={},
        own="like",
        others=[],
    )

    assert moves.put == []
