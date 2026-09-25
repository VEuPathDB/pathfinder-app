"""A strategy adopted from a separation is verified with exactly its controls."""

from __future__ import annotations

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.verify_dispatch import verification_scope, work_order
from pathfinder.tests._support.separation import ATTACHED_CONTROLS
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def test_the_scope_carries_the_attached_controls() -> None:
    deps = lead_deps(
        pipeline_state(domain=StrategyDomainState(attached_controls=ATTACHED_CONTROLS))
    )

    assert (
        verification_scope(deps, check_id="call_verify").controls == ATTACHED_CONTROLS
    )


def test_the_work_order_names_every_attached_control() -> None:
    assert work_order("check the adopted strategy", ATTACHED_CONTROLS, None) == (
        "Verification work order: check the adopted strategy\n"
        "Inspect the built strategy. Return a VerificationDelta.\n"
        "The strategy was adopted from a separation run. Run "
        "run_control_tests_on_step on its root step with exactly these controls, "
        "saved as control set 5f1c6a2e-0000-4000-8000-00000000c0de:\n"
        "positive_controls: PF3D7_0100600, PF3D7_0100800\n"
        "negative_controls: PF3D7_0508800"
    )


def test_a_strategy_with_no_attached_controls_gets_the_plain_order() -> None:
    assert work_order("check it", None, None) == (
        "Verification work order: check it\n"
        "Inspect the built strategy. Return a VerificationDelta."
    )
