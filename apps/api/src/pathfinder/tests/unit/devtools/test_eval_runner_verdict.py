"""The verdict an eval reads is the one on the strategy the checkpoint holds."""

from __future__ import annotations

from uuid import uuid4

from pydantic import JsonValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.devtools.eval_runner import (
    checkpointed_requirements,
    checkpointed_verdict,
)
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.evals.scoring import RequirementCounts
from pathfinder.tests.unit.ai.lead._budget_stop_turn import objection
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _tree(search_name: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_a", search_name=search_name),
    )


def _checked(
    *, then_edited: bool, digest: VerificationDigest | None = None
) -> dict[str, JsonValue]:
    """A checkpoint whose strategy a check judged, then a later message."""
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    judged = _tree("GenesByText")
    state.domain.answered_graph = judged
    state.domain.record_verdict(
        objection() if digest is None else digest,
        revision=strategy_revision(judged),
    )
    state.user_message_id = uuid4()
    if then_edited:
        state.domain.answered_graph = _tree("GenesByGoTerm")
    return state.model_dump(mode="json")


def test_the_verdict_read_is_the_one_on_the_strategy_as_it_stands() -> None:
    verdicts = {
        "a later message": checkpointed_verdict(_checked(then_edited=False)),
        "a later edit": checkpointed_verdict(_checked(then_edited=True)),
    }

    assert verdicts == {"a later message": False, "a later edit": None}


def test_a_pass_with_a_pending_check_is_not_verified() -> None:
    pending = objection().model_copy(
        update={"success": True, "pending_checks": ["step_de"]}
    )

    assert checkpointed_verdict(_checked(then_edited=False, digest=pending)) is False


def test_the_rows_an_eval_counts_are_the_verdicts_on_the_strategy() -> None:
    reviewed = objection().model_copy(
        update={
            "review": VerificationReview(
                requirements=[
                    RequirementCheck(
                        text="with a signal peptide",
                        turn=1,
                        answered_by=["s1"],
                        how="search",
                        status="met",
                    ),
                    RequirementCheck(
                        text="at least 2 transmembrane domains",
                        turn=1,
                        how="search",
                        status="unmet",
                    ),
                ]
            )
        }
    )

    counted = {
        "a later message": checkpointed_requirements(
            _checked(then_edited=False, digest=reviewed)
        ),
        "a later edit": checkpointed_requirements(
            _checked(then_edited=True, digest=reviewed)
        ),
    }

    assert counted == {
        "a later message": RequirementCounts(met=1, unmet=1, unexpressed=0),
        "a later edit": None,
    }
