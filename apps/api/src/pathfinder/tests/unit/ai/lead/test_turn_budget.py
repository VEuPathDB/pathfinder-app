"""The budget one Lead turn runs under, and what it says when it reaches it."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import pytest
from pydantic_ai.usage import RunUsage
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.ai.lead.reply_claims import machine_words
from pathfinder.ai.lead.turn_budget import (
    OFF_TOPIC_TURN_TOKEN_LIMIT,
    budget_stop_report,
    lead_turn_budget_message,
    lead_usage_limits,
    off_topic_budget_stop,
)
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.platform.config import get_settings
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    ADDED,
    ADDED_LINE,
    BUDGET,
    CHANGED_NOTHING,
    NOT_VERIFIED,
    OBJECTION,
    QUESTION,
    SITE_ID,
    STEP,
    STRATEGY_LINE,
    TITLE,
    URL,
    WORDS,
    built,
    built_session,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import user_intent

_CONFIGURED_LIMIT = 123456
_DEFAULT_LIMIT = 600_000
_SECOND_ROOT = "step_a1b2c3d4"
_TAIL = "Narrow the request and send it again, and I will start a fresh turn on it."


@pytest.fixture
def configured_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    monkeypatch.setenv("LEAD_TURN_TOKEN_LIMIT", str(_CONFIGURED_LIMIT))
    get_settings.cache_clear()
    yield _CONFIGURED_LIMIT
    get_settings.cache_clear()


def _usage(total_tokens: int) -> RunUsage:
    return RunUsage(input_tokens=total_tokens)


def _off_topic() -> UserIntent:
    return user_intent(IntentClassification.OFF_TOPIC)


def test_the_turn_budget_is_the_configured_token_ceiling(
    configured_limit: int,
) -> None:
    assert lead_usage_limits().total_tokens_limit == configured_limit


def test_the_turn_budget_covers_the_leads_own_calls_and_tokens() -> None:
    limits = lead_usage_limits()

    assert (limits.request_limit, limits.tool_calls_limit) == (80, 80)
    assert limits.total_tokens_limit == _DEFAULT_LIMIT


def test_each_turn_gets_its_own_limits_object() -> None:
    """One turn's ceiling is never the object another turn is judged by."""
    first = lead_usage_limits()

    assert lead_usage_limits() is not first
    assert lead_usage_limits() == first


def test_the_turn_budget_message_names_the_whole_turn_ceiling() -> None:
    assert lead_turn_budget_message() == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{_DEFAULT_LIMIT} tokens. {_TAIL}"
    )


def test_the_off_topic_stop_names_the_ceiling_it_stopped_at() -> None:
    assert off_topic_budget_stop(
        _usage(OFF_TOPIC_TURN_TOKEN_LIMIT + 1), _off_topic()
    ) == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{OFF_TOPIC_TURN_TOKEN_LIMIT} tokens. {_TAIL}"
    )


def test_the_stop_fires_only_for_an_off_topic_turn_over_its_ceiling() -> None:
    at = OFF_TOPIC_TURN_TOKEN_LIMIT
    fired = {
        "off topic, one token over": off_topic_budget_stop(_usage(at + 1), _off_topic())
        is not None,
        "off topic, at the ceiling": off_topic_budget_stop(_usage(at), _off_topic())
        is not None,
        "a question about the data, far over": off_topic_budget_stop(
            _usage(at * 2), user_intent(IntentClassification.FOLLOW_UP_QUESTION)
        )
        is not None,
        "not classified yet, far over": off_topic_budget_stop(_usage(at * 2), None)
        is not None,
    }

    assert fired == {
        "off topic, one token over": True,
        "off topic, at the ceiling": False,
        "a question about the data, far over": False,
        "not classified yet, far over": False,
    }


def _ledger(
    build: BuildSection, digest: VerificationDigest | None
) -> InvestigationLedger:
    return InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=build,
        verification=VerificationSection(digest=digest),
    )


def _nothing_built() -> StrategySession:
    return StrategySession(site_id=SITE_ID)


def _built_this_turn() -> TurnMarkers:
    return TurnMarkers(built=True, added_searches=[ADDED])


def _report(
    build: BuildSection,
    digest: VerificationDigest | None,
    session: StrategySession,
    *,
    turn: TurnMarkers | None = None,
    questions: Sequence[OpenQuestion] = (),
) -> str:
    return budget_stop_report(
        _ledger(build, digest),
        session,
        turn if turn is not None else _built_this_turn(),
        questions,
    )


def test_a_budget_stop_reports_the_step_the_turn_built() -> None:
    report = _report(
        built(),
        objection(),
        built_session(),
        questions=[OpenQuestion(question=QUESTION)],
    )

    assert report == "\n\n".join(
        [
            STRATEGY_LINE,
            ADDED_LINE,
            f"Verification objected: {OBJECTION}",
            QUESTION,
            BUDGET,
        ]
    )


def test_a_budget_stop_prints_no_internal_name() -> None:
    report = _report(
        built(),
        objection(),
        built_session(),
        questions=[OpenQuestion(question=QUESTION)],
    )

    assert machine_words(report) == []


def test_a_budget_stop_reports_a_passed_check() -> None:
    passed = objection().model_copy(update={"success": True})

    report = _report(built(), passed, built_session())

    assert report == "\n\n".join(
        [STRATEGY_LINE, ADDED_LINE, "Verification passed.", BUDGET]
    )


def test_a_budget_stop_before_any_check_says_the_turn_did_not_verify() -> None:
    report = _report(built(), None, built_session())

    assert report == "\n\n".join([STRATEGY_LINE, ADDED_LINE, NOT_VERIFIED, BUDGET])


def test_a_budget_stop_that_built_nothing_says_so() -> None:
    report = _report(BuildSection(), None, _nothing_built(), turn=TurnMarkers())

    assert report == f"Nothing was built.\n\n{CHANGED_NOTHING}\n\n{BUDGET}"


def test_a_budget_stop_keeps_frames_question_verbatim() -> None:
    report = _report(
        BuildSection(),
        None,
        _nothing_built(),
        turn=TurnMarkers(),
        questions=[OpenQuestion(question=QUESTION)],
    )

    assert report == "\n\n".join(
        ["Nothing was built.", CHANGED_NOTHING, QUESTION, BUDGET]
    )


def test_a_turn_that_wrote_nothing_says_so_over_an_earlier_build() -> None:
    report = _report(built(), None, built_session(), turn=TurnMarkers())

    assert report == "\n\n".join([STRATEGY_LINE, CHANGED_NOTHING, NOT_VERIFIED, BUDGET])


def test_an_edit_that_added_no_step_says_the_strategy_changed() -> None:
    report = _report(built(), None, built_session(), turn=TurnMarkers(edited=True))

    assert report == "\n\n".join(
        [
            STRATEGY_LINE,
            "This turn changed the strategy and added no step.",
            NOT_VERIFIED,
            BUDGET,
        ]
    )


def test_every_step_the_turn_added_is_named() -> None:
    second = AddedSearch(
        step_id=_SECOND_ROOT, search_display_name="Text", criterion_text="kinases"
    )
    turn = TurnMarkers(built=True, added_searches=[ADDED, second])

    report = _report(built(), None, built_session(), turn=turn)

    assert report.split("\n\n")[1] == (
        f'This turn added 2 steps: "{TITLE}" ({WORDS}); "Text" (kinases).'
    )


def test_an_objection_that_names_a_step_id_is_reported_without_it() -> None:
    naming = objection().model_copy(
        update={"prose": f"{STEP} keeps the wrong reference group."}
    )

    report = _report(built(), naming, built_session())

    assert report == "\n\n".join(
        [STRATEGY_LINE, ADDED_LINE, "Verification objected.", BUDGET]
    )


def test_a_budget_stop_before_the_step_reached_the_site_cites_no_count() -> None:
    report = _report(BuildSection(), None, built_session())

    assert report.split("\n\n")[0] == (
        f'The strategy holds 1 step; the final step is "{TITLE}".'
    )


def test_a_split_strategy_names_no_final_step() -> None:
    session = built_session()
    assert session.graph is not None
    session.graph.steps.update(
        flatten_tree(StrategyStepNode(id=_SECOND_ROOT, search_name="GenesByText"))
    )
    session.graph.recompute_roots()

    report = _report(built(), None, session)

    assert report.split("\n\n")[0] == (
        f"The strategy holds 2 steps. It is on VEuPathDB at {URL}."
    )


def test_a_budget_stop_cites_no_count_the_ledger_marks_out_of_date() -> None:
    stale = built().model_copy(
        update={"stale_build": StaleBuild(changed_nodes=[(STEP, 70, 12)])}
    )

    report = _report(stale, None, built_session())

    assert report.split("\n\n")[0] == (
        f'The strategy holds 1 step; the final step is "{TITLE}". The strategy '
        "changed on VEuPathDB after this conversation built it, so the count "
        "recorded here is out of date."
    )


def test_a_split_strategy_out_of_date_cites_no_link() -> None:
    session = built_session()
    assert session.graph is not None
    session.graph.steps.update(
        flatten_tree(StrategyStepNode(id=_SECOND_ROOT, search_name="GenesByText"))
    )
    session.graph.recompute_roots()
    stale = built().model_copy(
        update={"stale_build": StaleBuild(added_nodes=[_SECOND_ROOT])}
    )

    report = _report(stale, None, session)

    assert report.split("\n\n")[0] == (
        "The strategy holds 2 steps. The strategy changed on VEuPathDB after this "
        "conversation built it, so the count recorded here is out of date."
    )
