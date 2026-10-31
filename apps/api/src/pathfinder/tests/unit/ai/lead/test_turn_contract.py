"""Every rule of the Lead's turn contract, over the record its turn left."""

from __future__ import annotations

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.turn_contract import (
    OFF_TOPIC_REPLY_MAX_CHARS,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    AN_ESSAY,
    ASKING_REPLY,
    CLEAN_REPLY,
    CRITERION,
    DATASET,
    EDA_PROSE,
    REDIRECT,
    REPORTS_THE_STRATEGY,
    WITH_CODE,
    blame_deps,
    building_deps,
    eda_deps,
    framing_deps,
    kinds,
    off_topic_deps,
    open_frame_deps,
    reading_deps,
    reply,
)


class TestTheRecordTheTurnLeft:
    def test_the_record_reads_the_build_and_its_counts(self) -> None:
        record = turn_record(run_context_for(building_deps()))

        assert record.changed_strategy is True
        assert record.build_unverified is False
        assert record.build_outcome is not None
        assert record.facts.root_count == 132

    def test_the_record_names_the_criterion_waiting_for_its_analysis(self) -> None:
        record = turn_record(run_context_for(eda_deps()))

        assert record.turn_builds is True
        assert record.eda_criterion_pending is not None
        assert record.eda_criterion_pending.id == "c_essential"
        assert record.eda_criterion_pending.needs_analysis_on == DATASET

    def test_the_record_carries_the_stop_and_the_off_topic_verdict(self) -> None:
        deps = off_topic_deps()
        deps.last_phase_stop = PhaseStop(
            role="frame", reason=PhaseStopReason.BUDGET, tool_calls=60
        )

        record = turn_record(run_context_for(deps))

        assert record.off_topic is True
        assert record.last_phase_stop is not None
        assert record.last_phase_stop.tool_calls == 60


class TestTheUnverifiedBuildRule:
    def test_a_build_no_pass_checked_is_a_mismatch(self) -> None:
        deps = building_deps(verified=False)

        mismatches = reconcile(
            reply("I added the step."),
            turn_record(run_context_for(deps)),
        )

        assert [m.kind for m in mismatches] == ["unverified_build"]
        assert "1 step(s) on VEuPathDB" in mismatches[0].sentence
        assert "root count 132" in mismatches[0].sentence
        assert "verify_strategy" in mismatches[0].sentence

    def test_a_verified_build_is_no_mismatch(self) -> None:
        deps = building_deps(verified=True)

        assert kinds(deps, reply("I added the step.")) == []

    def test_a_dispatched_verification_that_failed_is_no_mismatch(self) -> None:
        deps = building_deps(verified=False)
        deps.state.turn_markers.verification_dispatched = True

        assert kinds(deps, reply("I added the step.")) == []

    def test_a_turn_that_built_nothing_is_no_mismatch(self) -> None:
        assert kinds(reading_deps(), reply(REPORTS_THE_STRATEGY)) == []


class TestTheUnbuiltEdaCriterionRule:
    def test_a_turn_that_opened_no_analysis_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(EDA_PROSE),
            turn_record(run_context_for(eda_deps())),
        )

        assert [m.kind for m in mismatches] == ["unbuilt_eda_criterion"]
        sentence = mismatches[0].sentence
        assert CRITERION in sentence
        assert DATASET in sentence
        assert "open_eda_analysis" in sentence
        assert "set_eda_filters" in sentence
        assert "preview_eda_subset" in sentence
        assert 'create_eda_step(criterion_id="c_essential")' in sentence
        assert "Never ask the user for an analysis specification" in sentence

    def test_a_turn_that_opened_the_analysis_stands(self) -> None:
        deps = eda_deps()
        deps.state.turn_markers.record_eda_dataset_opened(DATASET)

        assert kinds(deps, reply(EDA_PROSE)) == []

    def test_an_analysis_the_thread_already_holds_open_stands(self) -> None:
        deps = eda_deps()
        deps.state.domain.open_eda_analysis = OpenEdaAnalysis(
            dataset_id=DATASET, analysis_id="an-1"
        )

        assert kinds(deps, reply(EDA_PROSE)) == []

    def test_an_analysis_on_another_dataset_is_still_a_mismatch(self) -> None:
        deps = eda_deps()
        deps.state.turn_markers.record_eda_dataset_opened("DS_other")

        assert kinds(deps, reply(EDA_PROSE)) == ["unbuilt_eda_criterion"]

    def test_a_spec_with_no_waiting_criterion_stands(self) -> None:
        assert kinds(eda_deps(waiting=False), reply(EDA_PROSE)) == []

    def test_a_turn_that_does_not_build_stands(self) -> None:
        deps = eda_deps(classification=IntentClassification.FOLLOW_UP_QUESTION)

        assert kinds(deps, reply(EDA_PROSE)) == []


class TestTheUnrecordedQuestionRule:
    def test_an_open_value_asked_in_prose_is_the_question_card_s_rule(self) -> None:
        mismatches = reconcile(
            reply(ASKING_REPLY),
            turn_record(run_context_for(open_frame_deps())),
        )

        assert [m.kind for m in mismatches] == ["open_value_in_prose"]
        assert "question card (consult_user)" in mismatches[0].sentence

    def test_a_framed_turn_with_nothing_open_reads_no_question_in_prose(self) -> None:
        assert kinds(framing_deps(), reply(ASKING_REPLY)) == []

    def test_a_reply_from_a_turn_that_framed_nothing_stands(self) -> None:
        assert kinds(blame_deps(), reply(ASKING_REPLY)) == []

    def test_a_recorded_question_stands(self) -> None:
        report = reply(
            ASKING_REPLY,
            questions=[
                AskedQuestion(
                    question="Which gametocyte RNA-seq study?",
                    dimension=ConstraintKind.DATA_TYPE,
                    recommended_value="the asexual one",
                ),
            ],
        )

        assert kinds(framing_deps(), report) == []

    def test_a_reply_that_asks_nothing_stands(self) -> None:
        assert kinds(framing_deps(), reply(CLEAN_REPLY)) == []

    def test_a_completed_turn_stands(self) -> None:
        assert kinds(framing_deps(), reply(ASKING_REPLY, next_state="complete")) == ([])


class TestTheOffTopicEssayRule:
    def test_the_cap_on_an_out_of_scope_reply_is_four_hundred_characters(self) -> None:
        assert OFF_TOPIC_REPLY_MAX_CHARS == 400

    def test_a_short_reply_that_writes_code_stands(self) -> None:
        assert len(WITH_CODE) <= OFF_TOPIC_REPLY_MAX_CHARS
        assert kinds(off_topic_deps(), reply(WITH_CODE)) == []

    def test_a_reply_over_the_cap_is_a_mismatch(self) -> None:
        assert len(AN_ESSAY) > OFF_TOPIC_REPLY_MAX_CHARS

        mismatches = reconcile(
            reply(AN_ESSAY),
            turn_record(run_context_for(off_topic_deps())),
        )

        assert [m.kind for m in mismatches] == ["off_topic_essay"]
        assert str(OFF_TOPIC_REPLY_MAX_CHARS) in mismatches[0].sentence

    def test_the_two_sentence_redirect_stands(self) -> None:
        assert len(REDIRECT) <= OFF_TOPIC_REPLY_MAX_CHARS
        assert kinds(off_topic_deps(), reply(REDIRECT)) == []

    def test_a_question_about_the_data_may_answer_at_length_with_code(self) -> None:
        deps = off_topic_deps(IntentClassification.FOLLOW_UP_QUESTION)

        assert kinds(deps, reply(AN_ESSAY + WITH_CODE)) == []
