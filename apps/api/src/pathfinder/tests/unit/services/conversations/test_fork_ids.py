"""One id space per branch: the mint, and the chunk rewrite that reads it.

F5 of the thread-surgery invariants, at the level where it is pure.
"""

from __future__ import annotations

from pathfinder.services.conversations.fork_ids import (
    IdMint,
    rewrite_message_ids_in_chunk,
    rewrite_note_ids_in_payload,
    rewrite_scratchpad_ids_in_chunk,
)

_PARENT_MESSAGE = "11111111-1111-4111-8111-111111111111"
_OTHER_MESSAGE = "22222222-2222-4222-8222-222222222222"


def test_the_mint_answers_one_source_id_with_one_new_id() -> None:
    mint = IdMint()

    first = mint.of(_PARENT_MESSAGE)
    again = mint.of(_PARENT_MESSAGE)
    other = mint.of(_OTHER_MESSAGE)

    assert first == again
    assert first != other
    assert first != _PARENT_MESSAGE
    assert mint.mapping == {_PARENT_MESSAGE: first, _OTHER_MESSAGE: other}


def test_two_mints_never_agree() -> None:
    """Two branches of one anchor are two id spaces."""
    left, right = IdMint(), IdMint()

    assert left.of(_PARENT_MESSAGE) != right.of(_PARENT_MESSAGE)


def test_a_start_chunk_moves_into_the_branch_s_id_space() -> None:
    mint = IdMint()

    rewritten = rewrite_message_ids_in_chunk(
        {"type": "start", "messageId": _PARENT_MESSAGE},
        mint,
    )

    assert rewritten["messageId"] == mint.mapping[_PARENT_MESSAGE]
    assert rewritten["type"] == "start"


def test_a_user_message_chunk_moves_with_the_start_that_names_it() -> None:
    """One message, one id: the envelope and the start agree after the copy."""
    mint = IdMint()

    envelope = rewrite_message_ids_in_chunk(
        {
            "type": "user-message",
            "message": {"id": _PARENT_MESSAGE, "role": "user", "parts": []},
        },
        mint,
    )
    start = rewrite_message_ids_in_chunk(
        {"type": "start", "messageId": _PARENT_MESSAGE},
        mint,
    )

    assert envelope["message"]["id"] == start["messageId"]
    assert envelope["message"]["role"] == "user"


def test_a_withdrawn_prompt_stays_withdrawn_in_the_branch() -> None:
    mint = IdMint()

    envelope = rewrite_message_ids_in_chunk(
        {
            "type": "user-message",
            "message": {"id": _PARENT_MESSAGE, "role": "user", "parts": []},
        },
        mint,
    )
    withdrawn = rewrite_message_ids_in_chunk(
        {
            "type": "data-turn-withdrawn",
            "data": {"errorText": "declined", "messageId": _PARENT_MESSAGE},
        },
        mint,
    )

    assert withdrawn == {
        "type": "data-turn-withdrawn",
        "data": {"errorText": "declined", "messageId": envelope["message"]["id"]},
    }


def test_a_chunk_that_names_no_message_is_handed_on_unchanged() -> None:
    mint = IdMint()
    chunk = {"type": "data-task-progress", "data": {"percent": 50}}

    assert rewrite_message_ids_in_chunk(chunk, mint) == chunk
    assert mint.mapping == {}


def test_a_chunk_whose_message_key_holds_something_else_is_left_alone() -> None:
    mint = IdMint()
    chunk = {"type": "text-delta", "messageId": 7, "message": "not an envelope"}

    assert rewrite_message_ids_in_chunk(chunk, mint) == chunk
    assert mint.mapping == {}


def test_note_ids_are_swapped_only_at_note_id_keys() -> None:
    id_map = {"note-old": "note-new"}
    payload = {
        "id": "note-old",
        "noteId": "note-old",
        "title": "note-old",
        "nested": [{"source_note_id": "note-old"}, {"other": "note-old"}],
    }

    rewritten = rewrite_note_ids_in_payload(payload, id_map)

    assert rewritten["id"] == "note-new"
    assert rewritten["noteId"] == "note-new"
    assert rewritten["title"] == "note-old"
    assert rewritten["nested"][0]["source_note_id"] == "note-new"
    assert rewritten["nested"][1]["other"] == "note-old"


def test_a_scratchpad_tool_chunk_carries_the_branch_s_note_ids() -> None:
    id_map = {"note-old": "note-new"}

    rewritten = rewrite_scratchpad_ids_in_chunk(
        {
            "type": "tool-read_note",
            "input": {"noteId": "note-old"},
            "output": {"id": "note-old", "title": "proteases"},
        },
        id_map,
    )

    assert rewritten["input"]["noteId"] == "note-new"
    assert rewritten["output"]["id"] == "note-new"
    assert rewritten["output"]["title"] == "proteases"


def test_a_tool_chunk_that_is_not_the_scratchpad_s_is_left_alone() -> None:
    id_map = {"note-old": "note-new"}
    chunk = {"type": "tool-build_strategy", "input": {"id": "note-old"}}

    assert rewrite_scratchpad_ids_in_chunk(chunk, id_map) == chunk


def test_an_empty_note_map_rewrites_nothing() -> None:
    chunk = {"type": "tool-read_note", "input": {"noteId": "note-old"}}

    assert rewrite_scratchpad_ids_in_chunk(chunk, {}) == chunk
