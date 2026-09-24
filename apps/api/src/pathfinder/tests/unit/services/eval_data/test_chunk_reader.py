"""Reading turns and the verification verdict out of the chunk log.

Every chunk here is built by the code that writes it to the log, so a chunk
kind or a field the wire renames fails this suite rather than the extraction.
"""

from __future__ import annotations

from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.platform.types import JSONObject
from pydantic_ai.ui.vercel_ai.response_types import TextDeltaChunk

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.services.eval_data.chunk_reader import (
    LoggedChunk,
    read_turns,
    read_verification,
)
from pathfinder.tests._support.ledger import ledger_with


def _log(*chunks: JSONObject) -> list[LoggedChunk]:
    return [LoggedChunk.model_validate({"chunk": chunk}) for chunk in chunks]


def _user(
    text: str, message_id: str = "00000000-0000-0000-0000-000000000001"
) -> JSONObject:
    return user_message_chunk(
        message_id=message_id,
        parts=[{"type": "text", "text": text}],
    )


_SECOND_ID = "00000000-0000-0000-0000-000000000002"


def _delta(text: str) -> JSONObject:
    return TextDeltaChunk(id="lead-prose-1", delta=text).model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )


def _digest(
    *, success: bool, reason: str, pending: tuple[str, ...] = ()
) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE
        if success
        else PhaseDisposition.AWAITING_USER,
        prose="prose",
        reason=reason,
        success=success,
        key_findings=["root size holds"],
        pending_checks=list(pending),
    )


def _ledger(
    *, success: bool, reason: str = "checked", pending: tuple[str, ...] = ()
) -> JSONObject:
    """The ledger chunk, carrying the one section the reader looks at."""
    section = VerificationSection(
        digest=_digest(success=success, reason=reason, pending=pending)
    )
    chunk = ledger_update_event(ledger=ledger_with(section))
    return chunk.model_dump(by_alias=True, mode="json", exclude_none=True)


def test_a_user_message_opens_a_turn() -> None:
    turns = read_turns(_log(_user("find kinases")))

    assert [t.request for t in turns] == ["find kinases"]


def test_text_deltas_after_a_request_become_its_reply() -> None:
    turns = read_turns(_log(_user("find kinases"), _delta("Built "), _delta("it.")))

    assert turns[0].reply == "Built it."


def test_a_second_request_opens_a_second_turn() -> None:
    turns = read_turns(
        _log(
            _user("find kinases"),
            _delta("done"),
            _user("now narrow it", _SECOND_ID),
        ),
    )

    assert [t.request for t in turns] == ["find kinases", "now narrow it"]
    assert [t.reply for t in turns] == ["done", ""]


def test_chunks_before_the_first_request_are_dropped() -> None:
    turns = read_turns(_log(_delta("orphan"), _user("find kinases")))

    assert [t.request for t in turns] == ["find kinases"]


def test_a_request_is_redacted() -> None:
    turns = read_turns(_log(_user("mail me at ada@example.org")))

    assert turns[0].request == "mail me at [redacted-email]"


def test_a_reply_is_redacted() -> None:
    turns = read_turns(_log(_user("hi"), _delta("write to ada@example.org")))

    assert turns[0].reply == "write to [redacted-email]"


def test_a_log_with_no_ledger_has_no_verdict() -> None:
    assert read_verification(_log(_user("hi"))) is None


def test_the_last_ledger_wins() -> None:
    verdict = read_verification(
        _log(
            _user("hi"),
            _ledger(success=False, reason="one leaf empty"),
            _user("fix it"),
            _ledger(success=True, reason="root size holds"),
        ),
    )

    assert verdict is not None
    assert verdict.success
    assert verdict.reason == "root size holds"
    assert verdict.key_findings == ["root size holds"]


def test_the_verdict_keeps_its_pending_checks() -> None:
    verdict = read_verification(
        _log(_ledger(success=True, pending=("step_de",))),
    )

    assert verdict is not None
    assert (verdict.success, verdict.pending_checks, verdict.passed) == (
        True,
        ["step_de"],
        False,
    )


def test_a_ledger_without_a_digest_is_not_a_verdict() -> None:
    log = _log({"type": "data-ledger-update", "data": {"verification": {}}})

    assert read_verification(log) is None


def test_the_verdict_reason_is_redacted() -> None:
    verdict = read_verification(
        _log(_ledger(success=True, reason="ok ada@example.org")),
    )

    assert verdict is not None
    assert verdict.reason == "ok [redacted-email]"


def test_a_repeated_envelope_id_does_not_open_a_second_turn() -> None:
    """The log keeps the first envelope of an id, exactly as the reducer does."""
    turns = read_turns(
        _log(
            _user("find kinases"),
            _delta("Built "),
            _user("find kinases"),
            _delta("it."),
        ),
    )

    assert [t.request for t in turns] == ["find kinases"]
    assert [t.reply for t in turns] == ["Built it."]


def test_an_envelope_with_no_id_still_opens_a_turn() -> None:
    turns = read_turns(
        _log({"type": "user-message", "message": {"role": "user", "parts": []}}),
    )

    assert [t.request for t in turns] == [""]
