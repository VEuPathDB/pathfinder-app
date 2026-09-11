"""The per-dispatch ceiling and the model a phase runs on."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from assistant_core.platform.types import ReasoningEffort

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.sub_agent_tools import (
    CALLS_PER_CRITERION,
    MAX_CRITERIA_FLOOR,
    MAX_PHASE_TOOL_CALLS,
    MIN_PHASE_TOOL_CALLS,
    criteria_floor,
    phase_default_model_id,
    phase_override_kwargs,
    phase_usage_limits,
)
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.platform.config import get_settings
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_runtime,
    pipeline_state,
    requirement,
)


def _state() -> PipelineState:
    return pipeline_state(user_prompt="Find the kinases.")


def _spec(count: int) -> OperationalSpec:
    return OperationalSpec(
        goal="find the kinases",
        criteria=[
            Criterion(id=f"c{i}", text=f"criterion {i}") for i in range(1, count + 1)
        ],
    )


def _eight_criterion_thread() -> list[Constraint]:
    """Twelve requirements naming eight criteria, as a clarified thread holds."""
    return [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        requirement(ConstraintKind.DATA_TYPE, "phylogenetic profile", "orthology"),
        requirement(
            ConstraintKind.COMBINATION,
            "trophozoite evidence",
            "high expression AND mass spec evidence",
        ),
        requirement(ConstraintKind.DATA_TYPE, "variation dataset", "SNP calls"),
        requirement(ConstraintKind.PERCENTILE, "high expression", "top 10%"),
        requirement(ConstraintKind.STATISTICAL_THRESHOLD, "dN/dS", "> 1.0"),
        requirement(
            ConstraintKind.COMBINATION,
            "kinase identification",
            "domain OR ec number OR go term OR annotation",
        ),
        requirement(
            ConstraintKind.OTHER,
            "non-syntenic orthologs",
            "transform to orthologs",
        ),
        requirement(ConstraintKind.DATA_TYPE, "mass spec evidence", "proteomics"),
        requirement(ConstraintKind.STATISTICAL_THRESHOLD, "mass spec score", ">= 2"),
        requirement(ConstraintKind.DATA_TYPE, "expression dataset", "trophozoite"),
        requirement(ConstraintKind.STATISTICAL_THRESHOLD, "SNP count", ">= 5"),
    ]


class TestTheFloorComesFromTheThread:
    def test_an_empty_thread_leaves_the_declaration_alone(self) -> None:
        assert criteria_floor(_state()) == 0

    def test_the_spec_the_turn_started_from_sets_the_floor(self) -> None:
        state = _state()
        state.domain.spec_before_turn = _spec(8)
        assert criteria_floor(state) == 8

    def test_the_spec_the_thread_holds_sets_the_floor(self) -> None:
        state = _state()
        state.domain.operational_spec = _spec(6)
        assert criteria_floor(state) == 6

    def test_a_clarified_thread_floors_at_the_criteria_it_names(self) -> None:
        state = _state()
        requirements = _eight_criterion_thread()
        state.domain.requirements = requirements
        floor = criteria_floor(state)
        assert floor >= 8
        # A floor over-counts a shared criterion; it may not read as a request
        # larger than the requirements themselves.
        assert floor <= len(requirements)
        limit = phase_usage_limits(floor).tool_calls_limit
        assert limit is not None
        assert limit >= 8 * CALLS_PER_CRITERION

    def test_a_combination_names_one_criterion_per_term(self) -> None:
        state = _state()
        state.domain.requirements = [
            requirement(
                ConstraintKind.COMBINATION,
                "kinase identification",
                "domain OR ec number OR go term OR annotation",
            ),
        ]
        assert criteria_floor(state) == 4

    def test_a_restated_requirement_is_not_a_second_criterion(self) -> None:
        state = _state()
        state.domain.requirements = [
            requirement(ConstraintKind.DATA_TYPE, "expression dataset", "trophozoite"),
            requirement(ConstraintKind.DATA_TYPE, "expression dataset", "schizont"),
        ]
        assert criteria_floor(state) == 1

    def test_a_chatty_thread_cannot_spend_the_whole_turn(self) -> None:
        state = _state()
        state.domain.requirements = [
            requirement(ConstraintKind.DATA_TYPE, f"dataset {i}", f"study {i}")
            for i in range(40)
        ]
        assert criteria_floor(state) == MAX_CRITERIA_FLOOR
        limit = phase_usage_limits(criteria_floor(state)).tool_calls_limit
        assert limit == MAX_PHASE_TOOL_CALLS


class TestTheCeilingFollowsTheDeclaredSize:
    def test_a_large_problem_gets_more_than_a_small_one(self) -> None:
        small = phase_usage_limits(2).tool_calls_limit
        large = phase_usage_limits(9).tool_calls_limit
        assert small is not None
        assert large is not None
        assert large > small

    def test_nine_criteria_fit(self) -> None:
        limit = phase_usage_limits(9).tool_calls_limit
        assert limit is not None
        assert limit >= 9 * CALLS_PER_CRITERION

    def test_a_vocabulary_heavy_shape_fits(self) -> None:
        # Ten criteria on a site whose parameters carry large vocabularies.
        limit = phase_usage_limits(10).tool_calls_limit
        assert limit is not None
        assert limit >= 100

    def test_the_structure_pass_is_paid_for_too(self) -> None:
        # Binding every criterion and then having nothing left to combine them
        # spends the whole budget for no strategy.
        limit = phase_usage_limits(4).tool_calls_limit
        assert limit is not None
        assert limit > 4 * CALLS_PER_CRITERION


class TestTheCeilingStaysInRange:
    @pytest.mark.parametrize("declared", [0, 1, 2])
    def test_a_small_problem_still_gets_room_to_recover(self, declared: int) -> None:
        limit = phase_usage_limits(declared).tool_calls_limit
        assert limit == MIN_PHASE_TOOL_CALLS

    def test_an_overstated_count_is_capped(self) -> None:
        assert phase_usage_limits(500).tool_calls_limit == MAX_PHASE_TOOL_CALLS

    def test_a_negative_count_is_not_a_negative_budget(self) -> None:
        assert phase_usage_limits(-3).tool_calls_limit == MIN_PHASE_TOOL_CALLS


class TestTheOtherCeilingsHold:
    def test_requests_match_calls(self) -> None:
        limits = phase_usage_limits(9)
        assert limits.request_limit == limits.tool_calls_limit

    def test_the_token_ceiling_is_not_what_binds(self) -> None:
        assert phase_usage_limits(9).total_tokens_limit == 2_000_000


@pytest.fixture
def _real_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """These tests exercise the real model-translation path; the suite-wide
    default provider is ``mock``, which short-circuits the override."""
    monkeypatch.setenv("PATHFINDER_CHAT_PROVIDER", "default")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-for-model-translation")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _ctx(
    *,
    phase_models: dict[PhaseRole, str] | None = None,
    phase_reasoning: dict[PhaseRole, ReasoningEffort] | None = None,
) -> Context:
    models: dict[str, str] = dict((phase_models or {}).items())
    reasoning: dict[str, ReasoningEffort] = dict((phase_reasoning or {}).items())
    return dataclasses.replace(
        lead_runtime(),
        phase_models=models,
        phase_reasoning=reasoning,
    )


@pytest.mark.usefixtures("_real_provider")
def test_default_phase_model_comes_from_the_configured_tier() -> None:
    # With nothing pinned per phase, the model is the configured
    # (default_provider, default_tier) preset, and the stable ``provider:model``
    # id goes to pydantic-ai verbatim.
    kwargs = phase_override_kwargs(_ctx(), "frame")
    assert kwargs["model"] == "openai:gpt-5.6-luna"


@pytest.mark.usefixtures("_real_provider")
def test_anthropic_pick_enables_caching() -> None:
    kwargs = phase_override_kwargs(
        _ctx(phase_models={"frame": "anthropic:claude-opus-5"}),
        "frame",
    )
    assert kwargs["model"] == "anthropic:claude-opus-5"
    settings = kwargs["model_settings"]
    assert settings["anthropic_cache_instructions"] is True
    assert settings["anthropic_cache_tool_definitions"] is True
    assert settings["anthropic_cache_messages"] is True


@pytest.mark.usefixtures("_real_provider")
def test_openai_pick_carries_no_anthropic_flags() -> None:
    kwargs = phase_override_kwargs(
        _ctx(phase_models={"execution": "openai:gpt-5.6-terra"}),
        "execution",
    )
    assert kwargs["model"] == "openai:gpt-5.6-terra"
    assert "anthropic_cache_instructions" not in kwargs["model_settings"]


@pytest.mark.usefixtures("_real_provider")
def test_reasoning_effort_composes_with_caching() -> None:
    kwargs = phase_override_kwargs(
        _ctx(
            phase_models={"execution": "anthropic:claude-opus-5"},
            phase_reasoning={"execution": "high"},
        ),
        "execution",
    )
    settings = kwargs["model_settings"]
    assert settings["thinking"] == "high"
    assert settings["anthropic_cache_instructions"] is True


@pytest.mark.usefixtures("_real_provider")
def test_phase_default_model_id_stays_stable_for_cost() -> None:
    # The readback id used for cost attribution must remain the stable
    # ``provider:model`` catalog id.
    assert phase_default_model_id("frame") == "openai:gpt-5.6-luna"


@pytest.mark.usefixtures("_real_provider")
def test_configured_tier_actually_drives_phase_model_and_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching the default tier moves both the model and the reasoning effort
    for a phase the user has not pinned."""
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "quality", raising=False)

    frame = phase_override_kwargs(_ctx(), "frame")
    execution = phase_override_kwargs(_ctx(), "execution")

    assert frame["model"] == "openai:gpt-5.6-sol"
    assert frame["model_settings"]["thinking"] == "high"
    assert execution["model"] == "openai:gpt-5.6-terra"
    assert execution["model_settings"]["thinking"] == "medium"


@pytest.mark.usefixtures("_real_provider")
def test_explicit_phase_pick_outranks_the_configured_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "default_tier", "quality", raising=False)

    kwargs = phase_override_kwargs(
        _ctx(phase_models={"frame": "openai:gpt-5.6-terra"}), "frame"
    )
    assert kwargs["model"] == "openai:gpt-5.6-terra"
