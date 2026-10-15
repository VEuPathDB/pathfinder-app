"""A requirement only another site's search answers is sent to a new conversation on
that site, with the sentence the portal route already gives, and no question."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.frame_result_checks import hold_the_route_to_another_site
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.site_routes import site_route_sentence
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_ORTHOMCL = (
    "This needs OrthoMCL, whose searches answer it. [Open a new conversation "
    "there](/pathfinder/orthomcl/conversation); this conversation stays on PlasmoDB."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_route_names_the_site_and_links_a_new_conversation_there() -> None:
    assert site_route_sentence("plasmodb", "orthomcl") == _ORTHOMCL


def test_another_site_answers_names_its_site() -> None:
    with pytest.raises(ValidationError):
        RequirementReport(
            requirement="R1", problem=RequirementProblem.ANOTHER_SITE_ANSWERS
        )


def test_only_another_site_answers_names_a_site() -> None:
    with pytest.raises(ValidationError):
        RequirementReport(
            requirement="R1",
            problem=RequirementProblem.SITE_HAS_NO_SEARCH,
            site="orthomcl",
        )


async def test_a_pass_that_reports_another_site_answers_with_its_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _stub(*, agent_deps: AgentDeps, **_kwargs: object) -> FrameResult:
        del agent_deps
        return FrameResult(
            disposition="needs_user",
            summary="The profile search counts no absences.",
            requirement_problems=[
                RequirementReport(
                    requirement="R1",
                    problem=RequirementProblem.ANOTHER_SITE_ANSWERS,
                    site="orthomcl",
                )
            ],
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)
    deps = lead_deps(
        pipeline_state(
            user_prompt="genes in 3D7 but absent from at least 2 other strains",
            domain=StrategyDomainState(
                requirements=[
                    requirement(
                        ConstraintKind.OTHER,
                        "absence",
                        "absent from at least 2 other strains",
                    )
                ]
            ),
        )
    )

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="call_frame_1",
        work_order="present in 3D7, absent from at least 2 other strains",
    )

    assert result == FrameResult(
        disposition="needs_user",
        summary=site_route_sentence(
            "plasmodb",
            "orthomcl",
            'whose searches state "absent from at least 2 other strains"',
        ),
    )
    assert deps.state.domain.open_questions == []


async def test_a_route_for_a_number_no_requirement_holds_says_the_site_answers_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _stub(*, agent_deps: AgentDeps, **_kwargs: object) -> FrameResult:
        del agent_deps
        return _pass_with_a_route_to("orthomcl")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _stub)

    result = await run_frame(
        deps=lead_deps(pipeline_state()),
        parent_tool_call_id="call_frame_1",
        work_order="absent from at least 2 other strains",
    )

    assert result == FrameResult(disposition="needs_user", summary=_ORTHOMCL)


def test_the_lead_gives_any_sites_sentence_and_offers_no_switch() -> None:
    lead = _flat(LEAD_INSTRUCTIONS)

    assert "**A request only another site answers opens there.**" in lead
    assert 'the sentence that begins "This needs"' in lead


def test_frame_sends_a_count_across_species_to_orthomcl() -> None:
    frame = _flat(_FRAME_INSTRUCTIONS)

    assert "another_site_answers" in frame
    assert "GroupsByPhyleticPattern" in frame
    assert "FromGroups" in frame
    assert "`sequence` (proteins, the genes a request asks for)" in frame
    assert "answers the expression in words with the size of each list" in frame


def _pass_with_a_route_to(site: str) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        requirement_problems=[
            RequirementReport(
                requirement="R1",
                problem=RequirementProblem.ANOTHER_SITE_ANSWERS,
                site=site,
            )
        ],
    )


@pytest.mark.parametrize("site", ["plasmodb", "nowhere"])
def test_a_route_to_this_site_or_to_no_site_is_sent_back(site: str) -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(site_id="plasmodb"))

    with pytest.raises(ModelRetry, match="which is no other site"):
        hold_the_route_to_another_site(
            cast("RunContext[AgentDeps]", ctx), _pass_with_a_route_to(site)
        )


def test_a_route_to_another_site_passes() -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(site_id="plasmodb"))
    output = _pass_with_a_route_to("orthomcl")

    assert (
        hold_the_route_to_another_site(cast("RunContext[AgentDeps]", ctx), output)
        is output
    )
