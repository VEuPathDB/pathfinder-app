"""The ledger's own rules: staleness, site blame, and the two contradictions."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.ledger import (
    InvestigationLedger,
    build_contradiction,
)
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    ConstraintSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.domain.caveats import BuildCaveat
from pathfinder.domain.eda_thread import OpenEdaAnalysis
from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.staleness import StaleBuild

_BLAMING_REPLY = (
    "I kept every requirement you stated. Please try the build again once the "
    "site finishes refreshing the plan's search bindings; I will then "
    "materialize and verify it without changing these requirements."
)
_REAL_FAILURE_REPLY = (
    "VEuPathDB refused one step with a 422 on the organism parameter, so the "
    "build pushed two steps of three. Try again later once I re-bind that "
    "criterion."
)
_CLEAN_REPLY = (
    "The planning pass stopped on its call budget with three of eight criteria "
    "bound. I am running it again on the remaining five."
)
_COMBINATION = "mass spectrometry evidence OR DeRisi expression"


def _ledger(stale: StaleBuild | None = None) -> InvestigationLedger:
    return InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(stale_build=stale),
        verification=VerificationSection(),
    )


def test_summary_has_no_stale_marker_when_fresh() -> None:
    assert "STALE" not in _ledger().render_summary()


def test_summary_flags_stale_build() -> None:
    stale = StaleBuild(changed_nodes=[("step_a", 2862, 587)])
    summary = _ledger(stale).render_summary()
    assert "STALE" in summary
    assert "2862" in summary
    assert "587" in summary


def test_stale_marker_names_the_live_read_tool() -> None:
    stale = StaleBuild(changed_nodes=[("step_a", 10, 11)])
    assert "get_live_strategy_state" in _ledger(stale).render_summary()


def _ledger_with(analysis: OpenEdaAnalysis) -> InvestigationLedger:
    return _ledger().model_copy(update={"open_analysis": analysis})


def test_the_summary_names_the_open_analysis_and_its_count() -> None:
    summary = _ledger_with(
        OpenEdaAnalysis(
            dataset_id="DS_53f554ec6a", analysis_id="t4fszEJ", subset_previewed=True
        )
    ).render_summary()

    assert "## Open analysis\n- DS_53f554ec6a (t4fszEJ), subset counted" in summary
    assert "changed after the card" not in summary


def test_an_analysis_that_moved_past_its_card_is_shown_in_the_summary() -> None:
    summary = _ledger_with(
        OpenEdaAnalysis(
            dataset_id="DS_53f554ec6a",
            analysis_id="t4fszEJ",
            changed_after_the_card=True,
        )
    ).render_summary()

    assert "- DS_53f554ec6a (t4fszEJ), subset not counted" in summary
    assert "- changed after the card in this conversation" in summary


def test_a_thread_with_no_analysis_has_no_analysis_section() -> None:
    assert "## Open analysis" not in _ledger().render_summary()


def test_investigation_ledger_compose() -> None:
    ledger = _ledger()
    assert ledger.frame.present is False
    assert ledger.build.succeeded is False


def test_investigation_ledger_carries_no_sub_agent_call_count() -> None:
    """The thread's data-sub-agent-call parts are the only record of a dispatch."""
    assert "sub_agent_calls_this_turn" not in InvestigationLedger.model_fields
    assert "sub_agent_calls_total" not in InvestigationLedger.model_fields
    assert "Sub-agent calls" not in _ledger().render_summary()


class TestTheBuildRule:
    def test_a_turn_that_pushed_nothing_contradicts_success(self) -> None:
        contradiction = build_contradiction(BuildSection(), built_step_count=0)
        assert contradiction == BuildCaveat(pushed=0, failed=0, skipped=0, empty=0)

    def test_a_strategy_built_on_an_earlier_turn_does_not_contradict(self) -> None:
        assert [build_contradiction(BuildSection(), built_step_count=3)] == [None]

    def test_a_partial_build_contradicts_success(self) -> None:
        section = BuildSection(
            outcome=BuildOutcome(
                pushed_step_ids=["s1"],
                failed_steps=[
                    StepPushFailure(
                        step_id="s2", search_name="GenesByText", error="422"
                    )
                ],
            ),
            pushed_count=1,
            failed_count=1,
        )
        assert build_contradiction(section, built_step_count=1) == BuildCaveat(
            pushed=1, failed=1, skipped=0, empty=0
        )

    def test_a_clean_build_does_not_contradict(self) -> None:
        section = BuildSection(
            outcome=BuildOutcome(pushed_step_ids=["s1", "s2"]),
            pushed_count=2,
        )
        assert [build_contradiction(section, built_step_count=2)] == [None]


def _combination_requirement() -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=_COMBINATION,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def _combined_spec(operator: CombineOp) -> OperationalSpec:
    return OperationalSpec(
        goal="kinase drug targets",
        criteria=[
            Criterion(
                id="c_ms",
                text="trophozoite mass spectrometry evidence",
                search_name="GenesByMassSpec",
            ),
            Criterion(
                id="c_derisi",
                text="DeRisi timecourse expression",
                search_name="GenesByRNASeqEvidence",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=operator,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_ms"),
                    StructureNode(kind="leaf", criterion_id="c_derisi"),
                ],
            )
        ),
    )


class TestTheCombinationCheck:
    def _checked(self, operator: CombineOp) -> tuple[str, str]:
        [grounded] = ground_against_spec(
            [_combination_requirement()], _combined_spec(operator)
        )
        check = grounded_check(grounded)
        return check.status, check.requirement

    def test_an_intersected_or_fails(self) -> None:
        assert self._checked(CombineOp.INTERSECT) == (
            "fail",
            f"combination:{_COMBINATION}",
        )

    def test_a_unioned_or_passes(self) -> None:
        assert self._checked(CombineOp.UNION) == ("pass", f"combination:{_COMBINATION}")


class TestTheSummaryCarriesEveryDropReason:
    """The Lead decides what to do about a drop, so it reads the reason."""

    def _dropped(self) -> InvestigationLedger:
        spec = OperationalSpec(
            goal="essential drug targets",
            dropped=[
                DroppedCriterion(
                    text="essential in blood stages",
                    reason="no search on this site records blood-stage essentiality.",
                )
            ],
        )
        return InvestigationLedger(
            user_intent=None,
            frame=FrameSection(spec=spec),
            build=BuildSection(),
            verification=VerificationSection(),
        )

    def test_the_count_still_reports_one_drop(self) -> None:
        assert "- dropped: 1" in self._dropped().render_summary()

    def test_the_reason_reaches_the_summary_beside_its_criterion(self) -> None:
        summary = self._dropped().render_summary()

        assert (
            "essential in blood stages: no search on this site records "
            "blood-stage essentiality."
        ) in summary

    def test_a_frame_with_no_drop_adds_no_line(self) -> None:
        summary = _ledger().render_summary()

        assert "- dropped: 0" in summary
        assert "EDA-backed" not in summary


def test_a_long_list_of_captured_requirements_counts_what_it_leaves_out() -> None:
    section = ConstraintSection(
        composed=[
            Constraint(
                kind=ConstraintKind.OTHER,
                label=f"r{i}",
                requested_value=f"requirement {i}",
            )
            for i in range(22)
        ]
    )

    lines = section.render_composed()

    assert lines[:2] == [
        "- (2 more captured earlier)",
        "- r2 (other): 'requirement 2'",
    ]
    assert len(lines) == 21
