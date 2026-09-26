"""The first reply of every arc that builds or edits is one the real turn
contract accepts: it names each added search beside its reason, and the count.
A check of a built thread is accepted as a turn that wrote nothing."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from pathfinder.ai.lead.build_messages import (
    build_not_ready_message,
    build_would_replace_the_strategy,
)
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.models.mock.registry import ARCS
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    control_test_deps,
    reading_deps,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins
from pathfinder.tests.unit.ai.models._mock_turns import ADDED_SEARCH, Scene, names, play

SITES = ("plasmodb", "vectorbase")
_WRITES = {"build_strategy", "edit_strategy"}
_OWN = "own_experiment"


def _waiting_on(criterion: Criterion) -> str:
    """The refusal a build of a spec holding only ``criterion`` meets."""
    return build_not_ready_message(
        OperationalSpec(
            goal="genes up after a blood meal",
            criteria=[criterion],
            structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id=_OWN)),
        )
    )


def _building() -> LeadDeps:
    """A classified build turn on an empty thread, where the build is offered."""
    deps = lead_deps(
        pipeline_state(
            user_prompt="Genes up after a blood meal.", user_message_id=uuid4()
        ),
        intent=user_intent(IntentClassification.NEW_STRATEGY),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


# The refusals a build meets, as the build tool words them.
_REFUSALS = {
    "replaces": build_would_replace_the_strategy(3),
    "analysis": _waiting_on(
        Criterion(id=_OWN, text="up after a blood meal", needs_analysis_on="DS_x")
    ),
    "value": _waiting_on(
        Criterion(
            id=_OWN,
            text="in the top percentile",
            search_name="GenesByRNASeqtgonME49_Gregory_ME49_mRNA_rnaSeq_RSRCPercentile",
            open_params=[OpenSlot(param_name="samples_percentile_generic")],
        )
    ),
}
# What the check of the recorded control test says it found.
_TESTED = "7 of 10 positive controls recovered."


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("framed", [False, True])
@pytest.mark.parametrize("arc", sorted(ARCS))
def test_a_reply_that_writes_the_strategy_meets_the_contract(
    arc: str, site_id: str, framed: bool
) -> None:
    scene = Scene(instructions=framed_pins() if framed else "")
    calls = play("lead", site_id, f"Do it [[arc:{arc}]]", scene=scene)
    if not _WRITES & set(names(calls)):
        return
    report = LeadResponse.model_validate(calls[-1].args_as_dict())
    deps = building_deps() if report.strategy_changed else reading_deps()
    if report.strategy_changed:
        deps.state.turn_markers.added_searches = [ADDED_SEARCH]

    mismatches = reconcile(report, turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in mismatches] == []


@pytest.mark.parametrize("site_id", SITES)
def test_a_check_of_a_built_thread_meets_the_contract_as_a_read(site_id: str) -> None:
    digest = {"digest": {"success": True, "prose": _TESTED}}
    scene = Scene(instructions=framed_pins(), answers={"verify_strategy": digest})
    calls = play("lead", site_id, "Test it [[arc:controls-test]]", scene=scene)
    report = LeadResponse.model_validate(calls[-1].args_as_dict())

    mismatches = reconcile(report, turn_record(run_context_for(control_test_deps())))

    assert report.prose.startswith(_TESTED)
    assert not _WRITES & set(names(calls))
    assert [(m.kind, m.sentence) for m in mismatches] == []


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", ["single", "other-site-experiment"])
@pytest.mark.parametrize("refusal", sorted(_REFUSALS))
def test_a_refused_build_is_stated_in_plain_words(
    refusal: str, arc: str, site_id: str
) -> None:
    """The reply names no tool, no criterion id and no error text, checks
    nothing, and ends on the question that unblocks the build."""
    scene = Scene(refused={"build_strategy": _REFUSALS[refusal]})
    calls = play("lead", site_id, f"Do it [[arc:{arc}]]", scene=scene)
    report = LeadResponse.model_validate(calls[-1].args_as_dict())
    ctx = replace(run_context_for(_building()), retries={"build_strategy": 1})
    record = turn_record(ctx)

    mismatches = reconcile(report, record)

    assert record.refused_dispatches == ("build_strategy",)
    assert names(calls)[-2:] == ["build_strategy", "final_result"]
    assert report.strategy_changed is False
    assert (report.prose.startswith("Nothing was built: "), _OWN in report.prose) == (
        True,
        False,
    )
    assert [(m.kind, m.sentence) for m in mismatches] == []


def test_the_build_reply_names_the_search_beside_its_reason() -> None:
    calls = play("lead", "plasmodb", "[[arc:intersect]]")

    assert "- Predicted Signal Peptide, chosen for SignalP version" in str(
        calls[-1].args_as_dict()["prose"]
    )
