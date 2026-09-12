"""A verified turn leaves a case: the goal, the spec that reached a count, and
any zero-result step the turn recovered."""

from __future__ import annotations

from assistant_core.memory.tombstones import compute_content_hash
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
    ZeroResultStep,
)
from pathfinder.ai.lead.case_memory import collect_case_candidates
from pathfinder.ai.lead.memory_candidates import collect_memory_candidates
from pathfinder.domain.eda_thread import EdaAnalysisFacts, EdaExport
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases",
        interpreted_goal="Plasmodium falciparum kinases",
        organism_scope="Plasmodium falciparum",
        criteria=[
            Criterion(
                id="s1",
                text="kinase domain",
                search_name="GenesByGoTerm",
                role="seed",
                resolved_params={"go_term": StringValue(value="GO:0004672")},
            ),
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="s1")),
    )


def _outcome(count: int) -> BuildOutcome:
    return BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=330423363,
        counts={"s1": count},
        root_count=count,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesByGoTerm",
                count=count,
                status="ok" if count else "zero",
            ),
        ],
    )


def _state(
    *,
    outcome: BuildOutcome | None,
    success: bool = True,
    history: list[ZeroResultStep] | None = None,
) -> PipelineState:
    return pipeline_state(
        user_prompt="find the kinases",
        domain=StrategyDomainState(
            operational_spec=_spec(),
            original_request="find every kinase in P. falciparum",
            last_build_outcome=outcome,
            zero_result_history=list(history or []),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="done",
                reason="ok",
                success=success,
            ),
        ),
    )


def test_a_verified_build_leaves_one_outcome_case() -> None:
    candidates = collect_case_candidates(_state(outcome=_outcome(142)))

    assert len(candidates) == 1
    value, key = candidates[0]
    assert value.kind == "case"
    assert value.site_id == "plasmodb"
    assert value.content["case"] == "outcome"
    assert value.content["goal"] == "find every kinase in P. falciparum"
    assert value.content["root_count"] == 142
    assert value.content["structure"] == "GenesByGoTerm"
    assert value.content["criteria"] == [
        {
            "text": "kinase domain",
            "search_name": "GenesByGoTerm",
            "role": "seed",
            "params": {"go_term": "GO:0004672"},
        },
    ]
    assert key == f"case:{compute_content_hash(value.content)}"
    assert "142" in value.summary


def test_two_turns_on_the_same_goal_write_one_key() -> None:
    first = collect_case_candidates(_state(outcome=_outcome(142)))
    second = collect_case_candidates(_state(outcome=_outcome(142)))

    assert first[0][1] == second[0][1]


def test_a_different_count_is_a_different_case() -> None:
    first = collect_case_candidates(_state(outcome=_outcome(142)))
    second = collect_case_candidates(_state(outcome=_outcome(97)))

    assert first[0][1] != second[0][1]


def test_a_turn_with_no_build_leaves_no_case() -> None:
    assert collect_case_candidates(_state(outcome=None)) == []


def test_a_recovered_zero_step_leaves_a_recovery_case() -> None:
    history = [
        ZeroResultStep(search_name="GenesByGoTerm", criterion_text="kinase domain"),
    ]
    candidates = collect_case_candidates(
        _state(outcome=_outcome(142), history=history),
    )

    kinds = [value.content["case"] for value, _key in candidates]
    assert kinds == ["outcome", "recovery"]
    recovery = candidates[1][0]
    assert recovery.content["emptied_search"] == "GenesByGoTerm"
    assert recovery.content["fixed_params"] == {"go_term": "GO:0004672"}
    assert recovery.content["root_count"] == 142
    assert "GenesByGoTerm" in recovery.summary


def test_the_recovery_case_names_the_criterion_that_emptied() -> None:
    """The text recorded when the step emptied, not the one the fix renamed."""
    history = [
        ZeroResultStep(
            search_name="GenesByGoTerm",
            criterion_text="protein kinase activity",
        ),
    ]
    candidates = collect_case_candidates(
        _state(outcome=_outcome(142), history=history),
    )

    recovery = candidates[1][0]
    assert recovery.content["emptied_criterion"] == "protein kinase activity"
    assert "protein kinase activity" in recovery.summary


def test_a_step_that_is_still_empty_leaves_no_recovery_case() -> None:
    history = [
        ZeroResultStep(search_name="GenesByGoTerm", criterion_text="kinase domain"),
    ]
    candidates = collect_case_candidates(
        _state(outcome=_outcome(0), history=history),
    )

    assert [value.content["case"] for value, _key in candidates] == ["outcome"]


def test_a_build_records_the_searches_that_came_back_empty() -> None:
    state = _state(outcome=None)
    state.record_build(_outcome(0))

    assert state.domain.zero_result_history == [
        ZeroResultStep(
            search_name="GenesByGoTerm",
            criterion_text="kinase domain",
        ),
    ]


def test_the_history_records_each_search_once() -> None:
    state = _state(outcome=None)
    state.record_build(_outcome(0))
    state.record_build(_outcome(0))

    assert len(state.domain.zero_result_history) == 1


def test_the_turn_candidates_carry_the_case() -> None:
    candidates = collect_memory_candidates(_state(outcome=_outcome(142)))

    assert "case" in [value.kind for value, _key in candidates]


# ── The EDA arc: a built step with no spec behind it ─────────────────


def _eda_facts() -> EdaAnalysisFacts:
    return EdaAnalysisFacts(
        site_id="plasmodb",
        dataset_id="DS_53f554ec6a",
        study_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        study_display_name="Heat shock RNA-Seq (Su et al.)",
        display_name="febrile versus normal",
        num_filters=1,
        num_computations=1,
        filter_summaries=["Species is P. berghei"],
        entity_counts=[],
        can_export_rows=True,
    )


def _eda_export() -> EdaExport:
    return EdaExport(
        search_name="GenesByEdaVizWithCompute",
        step_id="step_1",
        dataset_id="DS_53f554ec6a",
        analysis_id="t4fszEJ",
        is_compute_backed=True,
        effect_size_threshold=1.0,
        significance_threshold=0.05,
        effect_direction="upAndDown",
    )


def _eda_outcome(count: int) -> BuildOutcome:
    return BuildOutcome(
        pushed_step_ids=["step_1"],
        wdk_strategy_id=330423363,
        counts={"step_1": count},
        root_count=count,
        node_results=[
            NodeResult(
                node_id="step_1",
                search_name="GenesByEdaVizWithCompute",
                count=count,
                status="ok" if count else "zero",
            ),
        ],
    )


def _eda_state(export: EdaExport | None) -> PipelineState:
    state = pipeline_state(
        user_prompt="export the genes up in the heat-shocked samples",
        domain=StrategyDomainState(
            original_request="which genes go up under heat shock in P. berghei",
            eda_analysis=_eda_facts(),
            last_build_outcome=_eda_outcome(1543),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="1543 genes",
                reason="verified",
                success=True,
            ),
        ),
    )
    state.turn_markers.eda_export = export
    return state


def test_an_eda_export_leaves_a_case_without_a_spec() -> None:
    """The EDA arc never frames criteria, and its turn still leaves a case."""
    candidates = collect_case_candidates(_eda_state(_eda_export()))

    assert len(candidates) == 1
    value, key = candidates[0]
    assert value.kind == "case"
    assert value.site_id == "plasmodb"
    assert value.content["case"] == "eda-export"
    goal = "which genes go up under heat shock in P. berghei"
    assert value.content["goal"] == goal
    assert value.content["study"] == "Heat shock RNA-Seq (Su et al.)"
    assert value.content["analysis"] == "febrile versus normal"
    assert value.content["filters"] == ["Species is P. berghei"]
    assert value.content["search_name"] == "GenesByEdaVizWithCompute"
    assert value.content["effect_size_threshold"] == 1.0
    assert value.content["significance_threshold"] == 0.05
    assert value.content["effect_direction"] == "upAndDown"
    assert value.content["exported_count"] == 1543
    assert key == f"case:{compute_content_hash(value.content)}"
    assert "1543" in value.summary
    assert "Heat shock RNA-Seq (Su et al.)" in value.summary


def test_a_turn_that_exported_nothing_leaves_no_eda_case() -> None:
    assert collect_case_candidates(_eda_state(None)) == []


def test_the_eda_case_travels_with_the_turn_candidates() -> None:
    candidates = collect_memory_candidates(_eda_state(_eda_export()))

    assert [value.content["case"] for value, _key in candidates] == ["eda-export"]


def test_a_subset_export_records_no_thresholds() -> None:
    """A subset export names no volcano cut, so the case states none."""
    export = _eda_export().model_copy(
        update={
            "is_compute_backed": False,
            "effect_size_threshold": None,
            "significance_threshold": None,
            "effect_direction": None,
            "search_name": "GenesByEdaSubset",
        },
    )
    (value, _key) = collect_case_candidates(_eda_state(export))[0]

    assert value.content["effect_size_threshold"] is None
    assert value.content["significance_threshold"] is None
    assert value.content["is_compute_backed"] is False


def test_an_export_with_no_measured_count_leaves_no_case() -> None:
    """A step VEuPathDB never sized has no number to remember."""
    state = _eda_state(_eda_export())
    outcome = state.domain.last_build_outcome
    assert outcome is not None
    outcome.counts = {}

    assert collect_case_candidates(state) == []


def test_an_eda_exported_turn_leaves_only_the_export_case() -> None:
    """A spec the turn framed but never built may not claim the export's count."""
    state = _eda_state(_eda_export())
    state.domain.operational_spec = _spec()
    candidates = collect_case_candidates(state)
    assert len(candidates) == 1
    value, _key = candidates[0]
    assert value.content["case"] == "eda-export"
