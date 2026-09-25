"""A case named after a long goal is cut at the last word that fits, and says so."""

from __future__ import annotations

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.case_memory import collect_case_candidates
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_LONG_GOAL = (
    "Find Plasmodium falciparum 3D7 genes with a signal peptide, at least two "
    "transmembrane domains and gametocyte-specific expression."
)


def _name_of(goal: str) -> str:
    spec = OperationalSpec(
        goal=goal,
        criteria=[
            Criterion(
                id="s1", text="signal peptide", search_name="GenesWithSignalPeptide"
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="s1")),
    )
    state = pipeline_state(
        domain=StrategyDomainState(
            answered_spec=spec,
            original_request=goal,
            last_build_outcome=BuildOutcome(
                pushed_step_ids=["s1"], counts={"s1": 9}, root_count=9
            ),
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="done",
                reason="ok",
                success=True,
            ),
        )
    )
    value, _key = collect_case_candidates(state)[0]
    return value.name


def test_a_long_goal_is_cut_at_a_word_boundary_with_an_ellipsis() -> None:
    assert len(_LONG_GOAL) == 130

    name = _name_of(_LONG_GOAL)

    assert name == (
        "Find Plasmodium falciparum 3D7 genes with a signal peptide, at least two "
        "transmembrane domains and..."
    )
    assert len(name) <= 120


def test_a_goal_that_fits_is_kept_whole() -> None:
    goal = "Find Plasmodium falciparum 3D7 genes with a signal peptide"

    assert _name_of(goal) == goal
