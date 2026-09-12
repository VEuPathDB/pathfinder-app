"""Ledger derivation over sample PipelineState shapes."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, ParamValue

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _state(**domain: object) -> PipelineState:
    return pipeline_state(domain=StrategyDomainState.model_validate(domain))


def _bound_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases",
        interpreted_goal="protein kinase genes",
        criteria=[
            Criterion(
                id="c1",
                text="protein kinases",
                search_name="GenesByGoTerm",
                resolved_params={},
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c1")),
    )


def test_no_state_yields_empty_ledger() -> None:
    ledger = derive_ledger(_state(), None)
    assert ledger.frame.spec is None
    assert ledger.frame.present is False
    assert ledger.frame.criteria_count == 0
    assert ledger.build.outcome is None
    assert ledger.verification.digest is None


def test_frame_present_with_bound_spec_is_ready_to_build() -> None:
    ledger = derive_ledger(_state(operational_spec=_bound_spec()), None)
    assert ledger.frame.present is True
    assert ledger.frame.criteria_count == 1
    assert ledger.frame.bound_count == 1
    assert ledger.frame.open_slot_count == 0
    assert ledger.frame.needs_user is False
    assert ledger.frame.ready_to_build is True


def test_frame_open_param_slot_needs_user() -> None:
    spec = _bound_spec()
    spec.criteria[0].open_params = [
        OpenSlot(criterion_id="c1", param_name="dataset", question="Which dataset?"),
    ]
    ledger = derive_ledger(_state(operational_spec=spec), None)
    assert ledger.frame.open_slot_count == 1
    assert ledger.frame.needs_user is True
    assert ledger.frame.ready_to_build is False


def test_frame_unbound_criterion_is_not_ready() -> None:
    spec = OperationalSpec(
        goal="x",
        criteria=[Criterion(id="c1", text="x", search_name="")],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c1")),
    )
    ledger = derive_ledger(_state(operational_spec=spec), None)
    assert ledger.frame.criteria_count == 1
    assert ledger.frame.bound_count == 0
    assert ledger.frame.ready_to_build is False


def test_frame_render_section_surfaces_criteria_and_structure() -> None:
    ledger = derive_ledger(_state(operational_spec=_bound_spec()), None)
    rendered = ledger.render_section("frame")
    assert "GenesByGoTerm" in rendered
    assert "protein kinases" in rendered


def test_build_section_recovery_kind_empty_result() -> None:
    outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=42,
        zero_step_ids=["s1"],
    )
    ledger = derive_ledger(_state(last_build_outcome=outcome), None)
    assert ledger.build.recovery_kind == "empty_result_review"
    assert ledger.build.needs_recovery is True
    assert ledger.build.succeeded is False


def test_build_section_recovery_kind_transient() -> None:
    outcome = BuildOutcome(
        failed_steps=[
            StepPushFailure(
                step_id="s1",
                search_name="X",
                error="WDK returned 503 - connection timed out",
            ),
        ],
    )
    ledger = derive_ledger(_state(last_build_outcome=outcome), None)
    assert ledger.build.recovery_kind == "transient_retry"


def test_build_section_recovery_kind_param_replan_on_vocab_error() -> None:
    outcome = BuildOutcome(
        failed_steps=[
            StepPushFailure(
                step_id="s1",
                search_name="X",
                error="Parameter validation failed: value not in vocab",
            ),
        ],
    )
    ledger = derive_ledger(_state(last_build_outcome=outcome), None)
    assert ledger.build.recovery_kind == "param_replan"


def test_build_section_succeeded() -> None:
    outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=1,
        root_count=10,
    )
    ledger = derive_ledger(_state(last_build_outcome=outcome), None)
    assert ledger.build.succeeded is True
    assert ledger.build.recovery_kind == "none"


def test_verification_section_present() -> None:
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="all good",
        reason="ok",
        success=True,
    )
    ledger = derive_ledger(_state(verification_digest=digest), None)
    assert ledger.verification.complete is True
    assert ledger.verification.successful is True


def test_differential_intent_surfaces_in_summary() -> None:
    intent = UserIntent(
        raw_text="X vs Y",
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="diff",
        is_differential=True,
        differential_sides=["gametocyte", "asexual blood stage"],
    )
    summary = derive_ledger(_state(), intent).render_summary()
    assert "differential" in summary


def _criterion(cid: str, percentile: float | None = None) -> Criterion:
    params: dict[str, ParamValue] = (
        {} if percentile is None else {"pct": NumberValue(value=percentile)}
    )
    return Criterion(
        id=cid, text=f"criterion {cid}", search_name=f"By{cid}", resolved_params=params
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(goal="g", criteria=list(criteria))


def _diff_state(
    before: OperationalSpec | None, after: OperationalSpec | None
) -> PipelineState:
    return pipeline_state(
        domain=StrategyDomainState(
            operational_spec=after,
            spec_before_turn=before,
        ),
    )


def test_ledger_renders_the_diff() -> None:
    before = _spec(_criterion("a"), _criterion("b"), _criterion("c", 80))
    after = _spec(_criterion("a"), _criterion("b"), _criterion("c", 90))

    summary = derive_ledger(_diff_state(before, after), None).render_summary()

    assert "kept 2, changed 1, added 0, dropped 0" in summary


def test_the_diff_names_a_dropped_criterion() -> None:
    before = _spec(_criterion("a"), _criterion("b"))
    after = _spec(_criterion("a"))

    ledger = derive_ledger(_diff_state(before, after), None)

    spec_diff = ledger.frame.spec_diff()
    assert spec_diff is not None
    assert [
        c.criterion_id for c in spec_diff.changes if c.disposition == "dropped"
    ] == ["b"]


def test_a_fresh_turn_has_no_diff() -> None:
    ledger = derive_ledger(_diff_state(None, _spec(_criterion("a"))), None)

    payload = ledger.model_dump(by_alias=True, mode="json", exclude_none=True)

    assert ledger.frame.spec_diff() is None
    assert "diff" not in payload["frame"]


def test_the_entry_spec_does_not_reach_the_wire() -> None:
    """The ledger chunk carries the comparison, never a second whole spec."""
    before = _spec(_criterion("a"), _criterion("b"))
    ledger = derive_ledger(_diff_state(before, _spec(_criterion("a"))), None)

    payload = ledger.model_dump(by_alias=True, mode="json", exclude_none=True)

    assert "specBeforeTurn" not in payload["frame"]
    assert payload["frame"]["diff"]["droppedCount"] == 1
