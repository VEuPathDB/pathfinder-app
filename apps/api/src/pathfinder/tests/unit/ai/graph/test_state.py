from __future__ import annotations

from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError
from veupathdb.domain.strategy.build_outcome import BuildOutcome
from veupathdb.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from veupathdb.domain.strategy.operational_spec import Criterion, OperationalSpec

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
    # a raw model trace — drop the field so checkpoints stay small.
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


class TestCheckpointsFromBeforeTheFbvFlip:
    """A checkpoint written by the five-phase pipeline must be REJECTED.

    ``PipelineState`` used to leave Pydantic's ``extra`` at its default, so a
    stale key was silently dropped. That is a compatibility shim for a shape
    that no longer exists, and it hides drift exactly the way an ``as Step``
    cast did: a field renamed in code goes quiet instead of loud.

    The state is strict now, and the old-shape checkpoints are truncated by
    the migration that accompanies it. PathFinder has not shipped, so there
    is nothing to stay compatible with.
    """

    def _old_shape(self) -> dict[str, object]:
        return {
            "conversation_id": str(uuid4()),
            "user_id": str(uuid4()),
            "site_id": "plasmodb",
            "mode": "strategy",
            "user_prompt": "gametocyte upregulated genes",
            # Fields the five-phase pipeline wrote and FRAME/BUILD/VERIFY removed.
            "active_plan": {"steps": [{"searchName": "GenesByTaxon"}]},
        }

    def test_a_pre_flip_checkpoint_is_rejected_loudly(self) -> None:
        with pytest.raises(ValidationError, match="active_plan"):
            PipelineState.model_validate(self._old_shape())

    def test_a_typo_in_a_field_name_is_rejected(self) -> None:
        # The real payoff: renaming a field can no longer half-land, with
        # writers setting a key readers silently ignore.
        payload = {
            "conversation_id": str(uuid4()),
            "user_id": str(uuid4()),
            "site_id": "plasmodb",
            "mode": "strategy",
            "operationl_spec": None,
        }

        with pytest.raises(ValidationError, match="operationl_spec"):
            PipelineState.model_validate(payload)

    def test_the_current_shape_still_validates(self) -> None:
        state = PipelineState.model_validate(
            {
                "conversation_id": str(uuid4()),
                "user_id": str(uuid4()),
                "site_id": "plasmodb",
                "mode": "strategy",
                "user_prompt": "gametocyte upregulated genes",
            }
        )

        assert state.domain.operational_spec is None


def test_a_dataset_is_not_sheeted_until_it_is_marked(
    base_state: PipelineState,
) -> None:
    assert base_state.domain.was_eda_sheet_shown("DS_53f554ec6a") is False


def test_marking_a_dataset_records_only_that_dataset(
    base_state: PipelineState,
) -> None:
    """A second sheet for the same study omits the vocabularies."""
    base_state.domain.mark_eda_sheet_shown("DS_53f554ec6a")
    assert base_state.domain.was_eda_sheet_shown("DS_53f554ec6a") is True
    assert base_state.domain.was_eda_sheet_shown("DS_eeca6a5476") is False


def _requirement(kind: ConstraintKind, label: str, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        label=label,
        requested_value=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _intent(
    raw_text: str,
    classification: IntentClassification,
    *constraints: Constraint,
) -> UserIntent:
    return UserIntent(
        raw_text=raw_text,
        classification=classification,
        inferred_goal="what the user asked for",
        explicit_constraints=list(constraints),
    )


_ASKED = "Find A. gambiae midgut protease genes near a regulatory motif."
_ANSWERED = "Near = within 1 kb upstream of the motif. Go ahead."

_ORGANISM = _requirement(ConstraintKind.ORGANISM, "organism", "Anopheles gambiae")
_PROXIMITY = _requirement(
    ConstraintKind.OTHER, "motif proximity", "within 1 kb upstream"
)


def _asked_intent() -> UserIntent:
    return _intent(_ASKED, IntentClassification.NEW_STRATEGY, _ORGANISM)


def _answered_intent() -> UserIntent:
    return _intent(_ANSWERED, IntentClassification.CLARIFICATION_RESPONSE, _PROXIMITY)


def _threaded(*intents: UserIntent) -> StrategyDomainState:
    domain = StrategyDomainState()
    for intent in intents:
        domain.record_intent(intent, request_text=intent.raw_text)
    return domain


def test_the_thread_accumulates_every_stated_requirement() -> None:
    domain = _threaded(_asked_intent(), _answered_intent())

    assert [c.requested_value for c in domain.requirements] == [
        "Anopheles gambiae",
        "within 1 kb upstream",
    ]


def test_a_repeated_requirement_is_recorded_once() -> None:
    domain = _threaded(_asked_intent(), _answered_intent(), _answered_intent())

    assert [c.requested_value for c in domain.requirements].count(
        "within 1 kb upstream"
    ) == 1


def test_a_clarification_never_becomes_the_original_request() -> None:
    domain = _threaded(_answered_intent(), _asked_intent())

    assert domain.original_request == _ASKED


def test_a_new_strategy_on_an_empty_thread_starts_the_requirements_over() -> None:
    domain = _threaded(_asked_intent(), _answered_intent())
    third = _intent(
        "Forget that. Find P. falciparum kinases.",
        IntentClassification.NEW_STRATEGY,
        _requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
    )

    domain.record_intent(third, request_text=third.raw_text)

    assert [c.requested_value for c in domain.requirements] == ["Plasmodium falciparum"]
    assert domain.original_request == third.raw_text


def test_a_new_strategy_on_a_built_thread_keeps_the_requirements() -> None:
    domain = _threaded(_asked_intent(), _answered_intent())
    domain.last_build_outcome = BuildOutcome(pushed_step_ids=["s1"])
    third = _intent("Also add the RNA-Seq filter.", IntentClassification.NEW_STRATEGY)

    domain.record_intent(third, request_text=third.raw_text)

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
