from __future__ import annotations

from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.graph.state import (
    PHASE_NAMES,
    PhaseDisposition,
    PhaseName,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec


@pytest.fixture
def base_state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


def test_phase_names_constant_matches_literal_args() -> None:
    assert set(PHASE_NAMES) == set(get_args(PhaseName))
    assert PHASE_NAMES == (
        "frame",
        "build",
        "verification",
    )


def test_state_minimum_construction(base_state: PipelineState) -> None:
    assert base_state.site_id == "plasmodb"
    assert base_state.mode == "strategy"
    assert base_state.user_prompt == ""
    assert base_state.user_parts == []
    assert base_state.domain.discovered_searches == {}
    assert base_state.domain.operational_spec is None
    assert base_state.domain.verification_digest is None
    assert base_state.domain.last_build_outcome is None
    assert base_state.domain.user_intent is None
    # Cross-phase / cross-turn context now flows through typed fields, not
    # a raw model trace - drop the field so checkpoints stay small.
    assert not hasattr(base_state, "message_history")
    assert not hasattr(base_state, "current_phase")
    assert not hasattr(base_state, "supervisor_log")
    assert not hasattr(base_state, "specialist_mode")


def test_state_carries_verification_digest(
    base_state: PipelineState,
) -> None:
    """Verification digest is the only typed exit signal under the Lead
    architecture; round-trip through JSON proves it survives the
    LangGraph checkpoint shape."""
    digest = VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Strategy ready.",
        reason="verification successful",
        success=True,
        key_findings=["1234 hits"],
    )
    state = base_state.model_copy(
        update={"domain": StrategyDomainState(verification_digest=digest)},
    )
    rehydrated = PipelineState.model_validate(state.model_dump(mode="json"))
    digest_back = rehydrated.domain.verification_digest
    assert digest_back is not None
    assert digest_back.disposition == PhaseDisposition.DONE
    assert digest_back.success is True
    assert digest_back.key_findings == ["1234 hits"]


def test_state_carries_operational_spec(base_state: PipelineState) -> None:
    spec = OperationalSpec(
        goal="find drug targets",
        interpreted_goal="find drug targets in P. falciparum",
        organism_scope="P. falciparum",
        criteria=[
            Criterion(id="c1", text="kinases", search_name="GenesByGoTerm"),
        ],
    )
    state = base_state.model_copy(
        update={"domain": StrategyDomainState(operational_spec=spec)},
    )
    rehydrated = PipelineState.model_validate(state.model_dump(mode="json"))
    spec_back = rehydrated.domain.operational_spec
    assert spec_back is not None
    assert spec_back.goal == "find drug targets"
    assert spec_back.criteria[0].search_name == "GenesByGoTerm"


def test_state_carries_discovered_searches(base_state: PipelineState) -> None:
    overview = SearchOverview(
        search_name="GenesByExpression",
        display_name="Genes by Expression",
        record_type="transcript",
        description="",
        parameter_names=["dataset"],
        required_params=["dataset"],
    )
    state = base_state.model_copy(
        update={
            "domain": StrategyDomainState(
                discovered_searches={"GenesByExpression": overview},
            ),
        },
    )
    rehydrated = PipelineState.model_validate(state.model_dump(mode="json"))
    searches = rehydrated.domain.discovered_searches
    assert "GenesByExpression" in searches
    assert searches["GenesByExpression"].display_name == "Genes by Expression"


def test_state_rejects_negative_total_tokens() -> None:
    """Sanity: PipelineState validation works on at least one field."""
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        turn_total_tokens=42,
    )
    assert state.turn_total_tokens == 42
    with pytest.raises(ValidationError):
        PipelineState.model_validate(
            {
                "conversation_id": str(uuid4()),
                "user_id": str(uuid4()),
                "site_id": "plasmodb",
                "mode": "strategy",
                "turn_total_tokens": "not a number",
            },
        )


class TestCheckpointsFromEarlierBuilds:
    """A checkpoint written by an earlier build still resumes.

    A field this build no longer declares is dropped; every record it still
    declares is rebuilt as its model, so the next turn reads models and not
    the mappings the checkpoint serializer falls back to.
    """

    def _earlier_shape(self) -> dict[str, object]:
        return {
            "conversation_id": str(uuid4()),
            "user_id": str(uuid4()),
            "site_id": "plasmodb",
            "mode": "strategy",
            "user_prompt": "gametocyte upregulated genes",
            "active_plan": {"steps": [{"searchName": "GenesByTaxon"}]},
            "domain": {
                "created_gene_set_ids": ["a1b2c3d4"],
                "last_build_outcome": {
                    "pushed_step_ids": ["step_a"],
                    "failed_steps": [],
                    "skipped_step_ids": [],
                    "wdk_strategy_id": 330642473,
                    "wdk_url": None,
                    "counts": {"step_a": 87},
                    "root_count": 87,
                    "zero_step_ids": [],
                    "node_results": [],
                },
            },
        }

    def test_a_dropped_field_is_discarded_and_the_records_rebuilt(self) -> None:
        state = PipelineState.model_validate(self._earlier_shape())
        assert isinstance(state.domain.last_build_outcome, BuildOutcome)
        assert state.domain.last_build_outcome.root_count == 87
        assert state.user_prompt == "gametocyte upregulated genes"

    def test_a_value_this_build_cannot_read_is_refused(self) -> None:
        stored = self._earlier_shape()
        stored["domain"] = {"last_build_outcome": 5}
        with pytest.raises(ValidationError, match="last_build_outcome"):
            PipelineState.model_validate(stored)


def _sheeted_studies(domain: StrategyDomainState) -> list[str]:
    """The study the thread holds a sheet for, as none or one dataset id."""
    sheet = domain.open_eda_sheet
    return [] if sheet is None else [sheet.dataset_id]


def test_no_eda_sheet_is_open_until_one_is_pinned(
    base_state: PipelineState,
) -> None:
    assert _sheeted_studies(base_state.domain) == []


def test_a_second_sheet_replaces_the_one_the_thread_holds(
    base_state: PipelineState,
) -> None:
    base_state.domain.pin_eda_sheet("DS_53f554ec6a", [])
    base_state.domain.pin_eda_sheet("DS_eeca6a5476", [])

    assert _sheeted_studies(base_state.domain) == ["DS_eeca6a5476"]


def test_an_applied_subset_closes_the_sheet(base_state: PipelineState) -> None:
    base_state.domain.pin_eda_sheet("DS_53f554ec6a", [])
    base_state.domain.close_eda_sheet()

    assert _sheeted_studies(base_state.domain) == []


def test_opening_another_study_closes_the_sheet(base_state: PipelineState) -> None:
    base_state.domain.pin_eda_sheet("DS_53f554ec6a", [])
    base_state.domain.close_eda_sheet_of_another_study("DS_eeca6a5476")

    assert _sheeted_studies(base_state.domain) == []


def test_reopening_the_same_study_keeps_its_sheet(base_state: PipelineState) -> None:
    """The sheet describes the study, which a fresh analysis does not change."""
    base_state.domain.pin_eda_sheet("DS_53f554ec6a", [])
    base_state.domain.close_eda_sheet_of_another_study("DS_53f554ec6a")

    assert _sheeted_studies(base_state.domain) == ["DS_53f554ec6a"]


def _requirement(kind: ConstraintKind, label: str, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        label=label,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _intent(
    classification: IntentClassification,
    *constraints: Constraint,
) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="what the user asked for",
        explicit_constraints=list(constraints),
    )


_ASKED = "Find A. gambiae midgut protease genes near a regulatory motif."
_ANSWERED = "Near = within 1 kb upstream of the motif. Go ahead."
_ABANDONED = "Forget that. Find P. falciparum kinases."

_ORGANISM = _requirement(ConstraintKind.ORGANISM, "organism", "Anopheles gambiae")
_PROXIMITY = _requirement(
    ConstraintKind.OTHER, "motif proximity", "within 1 kb upstream"
)


def _asked_intent() -> UserIntent:
    return _intent(IntentClassification.NEW_STRATEGY, _ORGANISM)


def _answered_intent() -> UserIntent:
    return _intent(IntentClassification.CLARIFICATION_RESPONSE, _PROXIMITY)


def _threaded(*messages: tuple[str, UserIntent]) -> StrategyDomainState:
    domain = StrategyDomainState()
    for text, intent in messages:
        domain.record_intent(intent, request_text=text)
    return domain


def test_the_thread_accumulates_every_stated_requirement() -> None:
    domain = _threaded((_ASKED, _asked_intent()), (_ANSWERED, _answered_intent()))

    assert [c.requested_value for c in domain.requirements] == [
        "Anopheles gambiae",
        "within 1 kb upstream",
    ]


def test_a_repeated_requirement_is_recorded_once() -> None:
    domain = _threaded(
        (_ASKED, _asked_intent()),
        (_ANSWERED, _answered_intent()),
        (_ANSWERED, _answered_intent()),
    )

    assert [c.requested_value for c in domain.requirements].count(
        "within 1 kb upstream"
    ) == 1


def test_a_clarification_never_becomes_the_original_request() -> None:
    domain = _threaded((_ANSWERED, _answered_intent()), (_ASKED, _asked_intent()))

    assert domain.original_request == _ASKED


def test_a_new_strategy_on_an_empty_thread_starts_the_requirements_over() -> None:
    domain = _threaded((_ASKED, _asked_intent()), (_ANSWERED, _answered_intent()))
    third = _intent(
        IntentClassification.NEW_STRATEGY,
        _requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
    )

    domain.take_a_new_request(strategy_has_steps=False)
    domain.record_intent(third, request_text=_ABANDONED)

    assert [c.requested_value for c in domain.requirements] == ["Plasmodium falciparum"]
    assert domain.original_request == _ABANDONED


def test_a_new_strategy_on_a_thread_with_steps_keeps_the_requirements() -> None:
    domain = _threaded((_ASKED, _asked_intent()), (_ANSWERED, _answered_intent()))
    third = _intent(IntentClassification.NEW_STRATEGY)

    domain.take_a_new_request(strategy_has_steps=True)
    domain.record_intent(third, request_text="Also add the RNA-Seq filter.")

    assert [c.requested_value for c in domain.requirements] == [
        "Anopheles gambiae",
        "within 1 kb upstream",
    ]
    assert domain.original_request == _ASKED


def _recorded_combinations(*batches: list[Constraint]) -> list[Constraint]:
    domain = StrategyDomainState()
    for batch in batches:
        domain.record_requirements(batch)
    return [c for c in domain.requirements if c.kind is ConstraintKind.COMBINATION]


def _combination(value: str) -> Constraint:
    return _requirement(ConstraintKind.COMBINATION, "evidence combination", value)


def test_a_new_combination_over_the_same_terms_supersedes_the_old_one() -> None:
    combos = _recorded_combinations(
        [_combination("mass spectrometry OR DeRisi expression")],
        [_combination("mass spectrometry AND DeRisi expression")],
    )

    assert len(combos) == 1
    assert combos[0].requested_value == "mass spectrometry AND DeRisi expression"


def test_a_combination_over_different_terms_accrues() -> None:
    combos = _recorded_combinations(
        [
            _combination("mass spectrometry OR DeRisi expression"),
            _requirement(
                ConstraintKind.COMBINATION,
                "annotation combination",
                "kinase annotation AND phyletic profile",
            ),
        ],
    )

    assert len(combos) == 2


_RETRY = "Fix the errors and try again."
_INVENTED = "Return the top 100 genes for each profile"


def _classified(*constraints: Constraint) -> UserIntent:
    return _intent(IntentClassification.CLARIFICATION_RESPONSE, *constraints)


def test_a_requirement_the_message_does_not_state_is_not_the_users() -> None:
    """A value the classifier composed is surfaced, and it gates nothing."""
    domain = StrategyDomainState()

    domain.record_intent(
        _classified(_requirement(ConstraintKind.OTHER, "profile breadth", _INVENTED)),
        request_text=_RETRY,
    )

    assert [(c.source, c.hard) for c in domain.requirements] == [
        (ConstraintSource.ASSUMED, False),
    ]


def test_a_requirement_the_message_states_is_the_users() -> None:
    domain = StrategyDomainState()

    domain.record_intent(
        _classified(_requirement(ConstraintKind.ORGANISM, "organism", "P. falciparum")),
        request_text="Find P. falciparum kinases, RNA-Seq only.",
    )

    assert [(c.source, c.hard) for c in domain.requirements] == [
        (ConstraintSource.USER_EXPLICIT, True),
    ]


def test_a_requirement_the_user_already_stated_stays_theirs() -> None:
    """A consult answer is the user's word, so restating it is not an invention."""
    domain = StrategyDomainState()
    domain.record_requirements(
        [_requirement(ConstraintKind.OTHER, "breadth", _INVENTED)]
    )

    domain.record_intent(
        _classified(_requirement(ConstraintKind.PERCENTILE, "breadth", _INVENTED)),
        request_text=_RETRY,
    )

    assert [(c.kind, c.source) for c in domain.requirements] == [
        (ConstraintKind.OTHER, ConstraintSource.USER_EXPLICIT),
        (ConstraintKind.PERCENTILE, ConstraintSource.USER_EXPLICIT),
    ]


def test_an_organism_the_user_abbreviated_is_still_theirs() -> None:
    """The classifier writes the binomial the user abbreviated."""
    domain = StrategyDomainState()

    domain.record_intent(
        _classified(
            _requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        ),
        request_text="Find P. falciparum kinases.",
    )

    assert [(c.source, c.hard) for c in domain.requirements] == [
        (ConstraintSource.USER_EXPLICIT, True),
    ]


def test_an_organism_the_message_never_names_is_not_theirs() -> None:
    domain = StrategyDomainState()

    domain.record_intent(
        _classified(
            _requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium vivax"),
        ),
        request_text="Find P. falciparum kinases.",
    )

    assert [(c.source, c.hard) for c in domain.requirements] == [
        (ConstraintSource.ASSUMED, False),
    ]
