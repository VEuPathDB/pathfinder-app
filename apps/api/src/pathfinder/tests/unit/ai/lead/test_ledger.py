"""The ledger's own rules: staleness, site blame, and the two contradictions."""

from __future__ import annotations

from veupathdb.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from veupathdb.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.ai.lead.ledger import (
    InvestigationLedger,
    blamed_the_site,
    build_contradiction,
    structure_contradiction,
)
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
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


def test_investigation_ledger_compose() -> None:
    ledger = _ledger()
    assert ledger.frame.present is False
    assert ledger.build.succeeded is False


def test_investigation_ledger_carries_no_sub_agent_call_count() -> None:
    """The thread's data-sub-agent-call parts are the only record of a dispatch."""
    assert "sub_agent_calls_this_turn" not in InvestigationLedger.model_fields
    assert "sub_agent_calls_total" not in InvestigationLedger.model_fields
    assert "Sub-agent calls" not in _ledger().render_summary()


def _blame(text: str, *, build: BuildSection) -> str:
    """Why the text may not stand, empty when it may."""
    return blamed_the_site(text, build=build) or ""


class TestTheSiteBlameMatcher:
    def test_a_wait_for_the_site_over_a_clean_build_is_blame(self) -> None:
        assert (
            _blame(_BLAMING_REPLY, build=BuildSection())
            == "it names 'the site' together with 'refresh'"
        )

    def test_a_reply_that_names_a_real_failure_is_not_refused(self) -> None:
        build = BuildSection(
            outcome=BuildOutcome(
                pushed_step_ids=["s1", "s2"],
                failed_steps=[
                    StepPushFailure(
                        step_id="s3", search_name="GenesByTaxon", error="422"
                    ),
                ],
            ),
            pushed_count=2,
            failed_count=1,
        )
        assert _blame(_REAL_FAILURE_REPLY, build=build) == ""

    def test_an_empty_step_is_a_real_failure(self) -> None:
        build = BuildSection(
            outcome=BuildOutcome(pushed_step_ids=["s1"]),
            pushed_count=1,
            zero_result_steps=["s1"],
        )
        assert _blame(_BLAMING_REPLY, build=build) == ""

    def test_a_reply_that_blames_nothing_passes(self) -> None:
        assert _blame(_CLEAN_REPLY, build=BuildSection()) == ""

    def test_naming_the_site_without_blame_passes(self) -> None:
        text = "The strategy holds 132 genes and is saved on VEuPathDB."
        assert _blame(text, build=BuildSection()) == ""


def _build_contradiction(section: BuildSection, built_step_count: int) -> str:
    """Why a success verdict cannot stand, empty when it can."""
    return build_contradiction(section, built_step_count=built_step_count) or ""


class TestTheBuildRule:
    def test_a_turn_that_pushed_nothing_contradicts_success(self) -> None:
        contradiction = build_contradiction(BuildSection(), built_step_count=0)
        assert contradiction == (
            "this turn built nothing and no step of the strategy is in VEuPathDB"
        )

    def test_a_strategy_built_on_an_earlier_turn_does_not_contradict(self) -> None:
        assert _build_contradiction(BuildSection(), built_step_count=3) == ""

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
        assert build_contradiction(section, built_step_count=1) == (
            "the build pushed 1 step, failed 1, skipped 0 and left 0 empty"
        )

    def test_a_clean_build_does_not_contradict(self) -> None:
        section = BuildSection(
            outcome=BuildOutcome(pushed_step_ids=["s1", "s2"], root_count=16),
            pushed_count=2,
        )
        assert _build_contradiction(section, built_step_count=2) == ""


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


def _structure_contradiction(
    requirements: list[Constraint], spec: OperationalSpec | None
) -> str:
    """Why a success verdict cannot stand, empty when it can."""
    return structure_contradiction(requirements, spec) or ""


class TestTheStructureRule:
    def test_an_intersected_or_contradicts_success(self) -> None:
        contradiction = structure_contradiction(
            [_combination_requirement()], _combined_spec(CombineOp.INTERSECT)
        )

        assert contradiction is not None
        assert _COMBINATION in contradiction
        assert "UNION" in contradiction
        assert "INTERSECT" in contradiction

    def test_a_unioned_or_does_not_contradict(self) -> None:
        assert (
            _structure_contradiction(
                [_combination_requirement()], _combined_spec(CombineOp.UNION)
            )
            == ""
        )

    def test_a_thread_with_no_spec_does_not_contradict(self) -> None:
        assert _structure_contradiction([_combination_requirement()], None) == ""

    def test_a_thread_that_stated_no_combination_does_not_contradict(self) -> None:
        assert _structure_contradiction([], _combined_spec(CombineOp.INTERSECT)) == ""
