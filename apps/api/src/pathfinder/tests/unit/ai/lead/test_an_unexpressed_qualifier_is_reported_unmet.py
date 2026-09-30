"""A word of a criterion that no search of the pass could state stands as an
unmet requirement: the ledger blocks on it, VERIFY cannot pass over it, and the
facts part shows it as a gap."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.ledger_render import render_constraints_full
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.verify_dispatch import _findings, _held
from pathfinder.domain.caveats import WordGap
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintStatus
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_TEXT = "all Plasmodium falciparum 3D7 genes, pseudogenes included"


def _deps(unexpressed: list[str]) -> LeadDeps:
    spec = OperationalSpec(
        goal=_TEXT,
        criteria=[
            Criterion(
                id="step_all",
                text=_TEXT,
                search_name="GenesByTaxon",
                search_display_name="Organism",
                role="seed",
                unexpressed_qualifiers=unexpressed,
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_all")
        ),
    )
    state = pipeline_state(
        user_prompt=_TEXT,
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.record_build(BuildOutcome(pushed_step_ids=["step_all"]))
    state.turn_markers.framed = True
    state.turn_markers.verified = True
    return lead_deps(state)


def test_the_ledger_blocks_on_the_word_no_search_states() -> None:
    ledger = derive_ledger(_deps(["pseudogenes"]).state, None)

    [unmet] = [
        g
        for g in ledger.constraints.grounded
        if g.status is ConstraintStatus.UNGROUNDABLE
    ]
    assert unmet.constraint.requested_value == "pseudogenes"
    assert ledger.constraints.blocking is True
    assert ledger.constraints.unmet_count == 1
    assert "'pseudogenes' -> ungroundable" in render_constraints_full(
        ledger.constraints
    )


def test_verification_cannot_pass_over_it() -> None:
    deps = _deps(["pseudogenes"])
    findings = _findings(deps, VerificationReview(), [])
    held = _held(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="5720 genes of Plasmodium falciparum 3D7.",
            reason="The count is plausible.",
            success=True,
        ),
        findings,
    )

    assert findings.gaps == [WordGap(word="pseudogenes")]
    assert (held.success, held.prose.splitlines()[0]) == (
        False,
        (
            "Verification cannot be reported: 'pseudogenes': no search the "
            "strategy runs states it. The checker's own account of the run follows."
        ),
    )


def test_the_word_is_a_gap_the_facts_part_shows() -> None:
    assert turn_facts(_deps(["pseudogenes"])).gaps == [WordGap(word="pseudogenes")]


def test_a_criterion_every_word_of_which_a_search_states_asks_nothing() -> None:
    deps = _deps([])
    ledger = derive_ledger(deps.state, None)

    assert ledger.constraints.blocking is False
    assert turn_facts(deps).gaps == []
