"""The reply of a turn that checked the strategy names every gap the check
found with what is missing, and states every caveat with its numbers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    CONTRACT_HEADING,
    hold_the_turn_contract,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.caveats import (
    Caveat,
    ControlsCaveat,
    Gap,
    RequirementGap,
    StructureGap,
    WordGap,
)
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_POSITIVES = [f"PF3D7_01{n:05d}" for n in range(80)]
_NEGATIVES = [f"PF3D7_14{n:05d}" for n in range(40)]
_V2_TEST = ControlTestEvidence(
    tested_label="Predicted Signal Peptide",
    positive=ControlSetEvidence(returned=_POSITIVES[:52], not_returned=_POSITIVES[52:]),
    negative=ControlSetEvidence(returned=_NEGATIVES[:2], not_returned=_NEGATIVES[2:]),
)
_V2_CAVEAT = ControlsCaveat(
    positives_returned=52, positives_total=80, negatives_returned=2, negatives_total=40
)
_UNMET = RequirementGap(text="at least 2 transmembrane domains", status="unmet")
_SILENT = "The strategy returns 479 genes with a predicted signal peptide."
_CAVEAT_REFUSAL = (
    "The check measured 52 of 80 positive controls returned; 2 of 40 negative "
    "controls returned. Your reply does not state it; give the numbers."
)
_UNMET_REFUSAL = (
    "The check found what the strategy does not answer: 'at least 2 "
    "transmembrane domains': nothing in the strategy answers it. Your reply "
    "does not say so; state each with what is missing."
)


def _word_refusal(word: str) -> str:
    return (
        f"The check found what the strategy does not answer: '{word}': no search "
        f"the strategy runs states it. Your reply does not say so; state each "
        f"with what is missing."
    )


def _checked(
    *, gaps: list[Gap] | None = None, caveats: list[Caveat] | None = None
) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Test this strategy against my controls.",
        user_message_id=uuid4(),
    )
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="controls tested",
            success=True,
            gaps=gaps or [],
            caveats=caveats or [],
        ),
        revision=strategy_revision(None),
    )
    state.turn_markers.verification_dispatched = True
    state.turn_markers.control_tests.append(
        ControlTestRun(tool_call_id="call_controls", evidence=_V2_TEST)
    )
    return lead_deps(state)


def test_a_reply_without_the_control_counts_is_refused() -> None:
    deps = _checked(caveats=[_V2_CAVEAT])

    found = reconcile(reply(_SILENT), turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in found] == [
        ("unstated_caveat", _CAVEAT_REFUSAL)
    ]


def test_a_reply_that_gives_the_control_counts_stands() -> None:
    report = reply(
        "The strategy returns 479 genes. 52 of 80 positive controls were "
        "returned, and 2 of 40 negative controls were returned."
    )

    assert kinds(_checked(caveats=[_V2_CAVEAT]), report) == []


def test_a_reply_silent_about_an_unmet_requirement_is_refused() -> None:
    deps = _checked(gaps=[_UNMET])

    found = reconcile(reply(_SILENT), turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in found] == [("unstated_gap", _UNMET_REFUSAL)]


def test_a_reply_that_names_each_gap_stands() -> None:
    gaps: list[Gap] = [
        _UNMET,
        StructureGap(expression="kinases OR phosphatases", built="INTERSECT"),
    ]
    report = reply(
        "The strategy does not require at least 2 transmembrane domains, and it "
        "joins kinases OR phosphatases with an intersection."
    )

    assert kinds(_checked(gaps=gaps), report) == []


def test_a_turn_that_did_not_check_owes_no_gap_or_caveat() -> None:
    deps = _checked(gaps=[_UNMET], caveats=[_V2_CAVEAT])
    deps.state.turn_markers.verification_dispatched = False

    assert kinds(deps, reply(_SILENT)) == []


def _framed(word: str) -> LeadDeps:
    text = "all Plasmodium falciparum 3D7 genes, pseudogenes included"
    spec = OperationalSpec(
        goal=text,
        criteria=[
            Criterion(
                id="step_all",
                text=text,
                search_name="GenesByTaxon",
                search_display_name="Organism",
                role="seed",
                unexpressed_qualifiers=[word],
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_all")
        ),
    )
    state = pipeline_state(
        user_prompt=text,
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.turn_markers.framed = True
    return lead_deps(state)


def test_a_framed_word_no_search_states_is_a_gap_without_a_check() -> None:
    deps = _framed("pseudogenes")

    found = reconcile(
        reply("The plan reads every gene."), turn_record(run_context_for(deps))
    )

    assert [(m.kind, m.sentence) for m in found] == [
        ("unstated_gap", _word_refusal("pseudogenes"))
    ]
    assert kinds(deps, reply("No search on the site states pseudogenes.")) == []


def test_the_correction_is_asked_once_per_turn() -> None:
    deps = _checked(caveats=[_V2_CAVEAT], gaps=[WordGap(word="exported")])
    ctx = run_context_for(deps)
    report = reply(_SILENT)

    with pytest.raises(ModelRetry) as refused:
        hold_the_turn_contract(ctx, report)

    assert str(refused.value).split("\n\n") == [
        CONTRACT_HEADING,
        _word_refusal("exported"),
        _CAVEAT_REFUSAL,
    ]
    assert hold_the_turn_contract(ctx, report) is report


_S10_ROW = RequirementGap(
    text="Also keep only those predicted to be exported to the host cell",
    status="unexpressed",
)
_S10_REPLY = (
    "One limitation remains: the site names this criterion Exported Protein, but "
    "does not expose a separate searchable field that specifically states "
    "'exported to the host cell.'"
)


def test_a_reply_that_names_the_rows_words_states_the_gap() -> None:
    assert kinds(_checked(gaps=[_S10_ROW]), reply(_S10_REPLY)) == []


def test_a_reply_that_names_none_of_the_rows_words_is_refused() -> None:
    report = reply("The strategy returns 25 genes.")

    assert kinds(_checked(gaps=[_S10_ROW]), report) == ["unstated_gap"]


def test_the_e2_reply_states_its_unexpressed_row() -> None:
    gap = RequirementGap(text="Use sense counts", status="unexpressed")
    report = reply(
        "The verification found one unmet requirement: **Use sense counts**. The "
        "built analysis does not record the count type, so the strategy returns "
        "201 DE genes without verified sense-count selection."
    )

    assert kinds(_checked(gaps=[gap]), report) == []
