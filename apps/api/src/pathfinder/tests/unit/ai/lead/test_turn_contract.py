"""Every rule of the Lead's turn contract, over the record its turn left."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.turn_contract import (
    OFF_TOPIC_REPLY_MAX_CHARS,
    LeadResponse,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.evidence import SourceReference
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    AN_ESSAY,
    ASKING_REPLY,
    BLAMING_REPLY,
    CLAIMS_A_CHANGE,
    CLAIMS_A_GENE_SET_ENRICHMENT,
    CLEAN_REPLY,
    CONTROL_SET_CLAIM,
    CRITERION,
    DATASET,
    DENIES_A_CONTROL_SET,
    DENIES_A_GENE_SET,
    EDA_PROSE,
    GENE_SET_REPLY,
    LISTS_SAVED_CONTROL_SETS,
    LISTS_SAVED_GENE_SETS,
    NAMES_A_CONTROL_SET_IN_A_SECOND_CLAUSE,
    REAL_FAILURE_REPLY,
    REDIRECT,
    REPORTS_THE_STRATEGY,
    WITH_CODE,
    blame_deps,
    building_deps,
    control_source_deps,
    eda_deps,
    framing_deps,
    kinds,
    off_topic_deps,
    reading_deps,
    reply,
)


class TestTheRecordTheTurnLeft:
    def test_the_record_reads_the_build_and_its_counts(self) -> None:
        record = turn_record(run_context_for(building_deps()))

        assert record.changed_strategy is True
        assert record.build_unverified is False
        assert record.build_outcome is not None
        assert record.build_outcome.root_count == 132

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
            reply("I added the step.", changed=True),
            turn_record(run_context_for(deps)),
        )

        assert [m.kind for m in mismatches] == ["unverified_build"]
        assert "1 step(s) on VEuPathDB" in mismatches[0].sentence
        assert "root count 132" in mismatches[0].sentence
        assert "verify_strategy" in mismatches[0].sentence

    def test_a_verified_build_is_no_mismatch(self) -> None:
        deps = building_deps(verified=True)

        assert kinds(deps, reply("I added the step.", changed=True)) == []

    def test_a_dispatched_verification_that_failed_is_no_mismatch(self) -> None:
        deps = building_deps(verified=False)
        deps.state.turn_markers.verification_dispatched = True

        assert kinds(deps, reply("I added the step.", changed=True)) == []

    def test_a_turn_that_built_nothing_is_no_mismatch(self) -> None:
        assert kinds(reading_deps(), reply(REPORTS_THE_STRATEGY)) == []


class TestTheMisreportedChangeRule:
    def test_a_claimed_change_the_turn_never_made_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(CLAIMS_A_CHANGE, changed=True),
            turn_record(run_context_for(reading_deps())),
        )

        assert [m.kind for m in mismatches] == ["misreported_change"]
        assert "no build, edit, delete, clear or export" in mismatches[0].sentence
        assert "3 step(s)" in mismatches[0].sentence
        assert "root count 1" in mismatches[0].sentence

    def test_a_change_the_reply_leaves_out_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(REPORTS_THE_STRATEGY, changed=False),
            turn_record(run_context_for(building_deps())),
        )

        assert [m.kind for m in mismatches] == ["misreported_change"]
        assert "strategy_changed to true" in mismatches[0].sentence

    def test_a_reported_change_that_matches_the_build_stands(self) -> None:
        assert kinds(building_deps(), reply("I added the step.", changed=True)) == []

    def test_a_reply_that_reports_no_change_on_a_read_turn_stands(self) -> None:
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


class TestTheBlamedSiteRule:
    def test_a_blaming_reply_is_a_mismatch_and_names_the_real_stop(self) -> None:
        deps = blame_deps()
        deps.last_phase_stop = PhaseStop(
            role="frame",
            reason=PhaseStopReason.BUDGET,
            tool_calls=60,
            criteria_bound=3,
            criteria_declared=8,
        )

        mismatches = reconcile(
            reply(BLAMING_REPLY),
            turn_record(run_context_for(deps)),
        )

        assert [m.kind for m in mismatches] == ["blamed_the_site", "unfinished_work"]
        assert (
            "the framing pass stopped on its call budget after 60 calls"
            in mismatches[0].sentence
        )

    def test_a_reply_naming_a_real_wdk_failure_stands(self) -> None:
        deps = blame_deps()
        deps.state.domain.last_build_outcome = BuildOutcome(
            pushed_step_ids=["s1", "s2"],
            failed_steps=[
                StepPushFailure(step_id="s3", search_name="GenesByTaxon", error="422"),
            ],
        )

        assert kinds(deps, reply(REAL_FAILURE_REPLY)) == []

    def test_a_reply_that_blames_nothing_stands(self) -> None:
        assert kinds(blame_deps(), reply(CLEAN_REPLY)) == []


class TestTheUnrecordedQuestionRule:
    def test_a_question_the_reply_does_not_record_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(ASKING_REPLY),
            turn_record(run_context_for(framing_deps())),
        )

        assert [m.kind for m in mismatches] == ["unrecorded_question"]
        assert "asked_questions" in mismatches[0].sentence

    def test_a_reply_from_a_turn_that_framed_nothing_stands(self) -> None:
        assert kinds(blame_deps(), reply(ASKING_REPLY)) == []

    def test_a_recorded_question_stands(self) -> None:
        report = reply(
            ASKING_REPLY,
            questions=[
                OpenQuestion(
                    question="Which gametocyte RNA-seq study?",
                    dimension=ConstraintKind.DATA_TYPE,
                    recommended_value="the 3D7 one",
                ),
            ],
        )

        assert kinds(framing_deps(), report) == []

    def test_a_reply_that_asks_nothing_stands(self) -> None:
        assert kinds(framing_deps(), reply(CLEAN_REPLY)) == []

    def test_a_completed_turn_stands(self) -> None:
        assert kinds(framing_deps(), reply(ASKING_REPLY, next_state="complete")) == ([])


class TestTheControlSetAReplyClaims:
    """A durable artifact the reply names is one the turn wrote."""

    def test_a_control_set_the_turn_never_wrote_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(CONTROL_SET_CLAIM),
            turn_record(run_context_for(control_source_deps())),
        )

        assert [m.kind for m in mismatches] == ["unwritten_control_set"]
        sentence = mismatches[0].sentence
        assert "build_control_set" in sentence
        assert "rhoptry positives" in sentence
        assert "102 genes" in sentence

    def test_the_control_set_the_turn_wrote_stands(self) -> None:
        deps = control_source_deps(wrote_control_set=True)

        assert kinds(deps, reply(CONTROL_SET_CLAIM)) == []

    def test_a_reply_that_names_what_the_turn_saved_stands(self) -> None:
        assert kinds(control_source_deps(), reply(GENE_SET_REPLY)) == []

    def test_listing_the_control_sets_a_user_already_has_stands(self) -> None:
        assert kinds(control_source_deps(), reply(LISTS_SAVED_CONTROL_SETS)) == []

    def test_a_control_set_named_in_a_later_clause_stands(self) -> None:
        deps = control_source_deps()

        assert kinds(deps, reply(NAMES_A_CONTROL_SET_IN_A_SECOND_CLAUSE)) == []

    def test_saying_no_control_set_was_created_stands(self) -> None:
        assert kinds(control_source_deps(), reply(DENIES_A_CONTROL_SET)) == []


class TestTheGeneSetAReplyClaims:
    """A saved gene set the reply names is one this turn saved."""

    def test_a_gene_set_the_turn_never_saved_is_a_mismatch(self) -> None:
        deps = control_source_deps(saved_gene_set=False, wrote_control_set=True)

        mismatches = reconcile(
            reply(GENE_SET_REPLY),
            turn_record(run_context_for(deps)),
        )

        assert [m.kind for m in mismatches] == ["unwritten_gene_set"]
        sentence = mismatches[0].sentence
        assert "save_gene_set" in sentence
        assert "rhoptry controls" in sentence

    def test_the_gene_set_the_turn_saved_stands(self) -> None:
        assert kinds(control_source_deps(), reply(GENE_SET_REPLY)) == []

    def test_a_saved_set_called_a_control_set_is_corrected_once(self) -> None:
        """The turn saved a gene set, so only the wrong noun is a mismatch."""
        assert kinds(control_source_deps(), reply(CONTROL_SET_CLAIM)) == [
            "unwritten_control_set",
        ]

    def test_listing_the_gene_sets_a_user_already_has_stands(self) -> None:
        deps = control_source_deps(saved_gene_set=False)

        assert kinds(deps, reply(LISTS_SAVED_GENE_SETS)) == []

    def test_saying_no_gene_set_was_saved_stands(self) -> None:
        deps = control_source_deps(saved_gene_set=False)

        assert kinds(deps, reply(DENIES_A_GENE_SET)) == []

    def test_an_enrichment_over_a_gene_set_saves_none_and_claims_none(self) -> None:
        deps = control_source_deps(saved_gene_set=False)

        assert kinds(deps, reply(CLAIMS_A_GENE_SET_ENRICHMENT)) == []


class TestTheOffTopicEssayRule:
    def test_the_cap_on_an_out_of_scope_reply_is_four_hundred_characters(self) -> None:
        assert OFF_TOPIC_REPLY_MAX_CHARS == 400

    def test_a_reply_that_writes_code_is_a_mismatch(self) -> None:
        mismatches = reconcile(
            reply(WITH_CODE),
            turn_record(run_context_for(off_topic_deps())),
        )

        assert [m.kind for m in mismatches] == ["off_topic_essay"]
        assert "code" in mismatches[0].sentence

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


# What the recorder put on the markers after one literature search answered.
_A_PAPER_REFERENCES = (
    "https://pubmed.ncbi.nlm.nih.gov/16460820/",
    "10.1016/j.molbiopara.2006.01.001",
    "16460820",
    "https://europepmc.org/article/MED/16460820",
)
_RECORD_URL = "https://toxodb.org/toxo/app/record/gene/TGME49_233460"


class TestTheSourcesTheReplyLists:
    def test_a_paper_this_turn_retrieved_passes(self) -> None:
        deps = reading_deps()
        for reference in _A_PAPER_REFERENCES:
            deps.state.turn_markers.record_retrieved_source(reference)
        report = reply(
            "The SRS family is reviewed there.",
            sources=[
                SourceReference(
                    kind="literature",
                    label="SAG1-related sequences",
                    doi="10.1016/j.molbiopara.2006.01.001",
                ),
            ],
        )

        assert kinds(deps, report) == []

    def test_a_reference_no_read_of_this_turn_returned_is_one_mismatch(self) -> None:
        deps = reading_deps()
        for reference in _A_PAPER_REFERENCES:
            deps.state.turn_markers.record_retrieved_source(reference)
        report = reply(
            "The SRS family is reviewed there.",
            sources=[
                SourceReference(
                    kind="literature",
                    label="A review nobody read",
                    doi="10.1000/invented.2026.99",
                ),
            ],
        )

        assert kinds(deps, report) == ["unretrieved_source"]

    def test_a_source_the_reader_cannot_open_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="a url, a DOI or a PMID"):
            LeadResponse.model_validate(
                {
                    "prose": "A review says so.",
                    "sources": [{"kind": "literature", "label": "A review"}],
                }
            )

    def test_a_doi_written_only_in_the_prose_is_not_scanned(self) -> None:
        deps = reading_deps()
        report = reply("See doi:10.1000/invented.2026.99 for the review.")

        assert kinds(deps, report) == []

    def test_the_record_this_turn_read_is_a_source_it_can_cite(self) -> None:
        deps = reading_deps()
        deps.state.turn_markers.record_retrieved_source(_RECORD_URL)
        report = reply(
            "The record says one exon.",
            sources=[
                SourceReference(
                    kind="record",
                    label="TGME49_233460 on ToxoDB",
                    url=_RECORD_URL,
                ),
            ],
        )

        assert kinds(deps, report) == []

    def test_the_same_reference_is_matched_whatever_form_it_is_written_in(self) -> None:
        deps = reading_deps()
        for reference in _A_PAPER_REFERENCES:
            deps.state.turn_markers.record_retrieved_source(reference)
        report = reply(
            "The review states it.",
            sources=[
                SourceReference(
                    kind="literature",
                    label="SAG1-related sequences",
                    url="https://doi.org/10.1016/j.molbiopara.2006.01.001",
                    pmid="16460820",
                ),
            ],
        )

        assert kinds(deps, report) == []
