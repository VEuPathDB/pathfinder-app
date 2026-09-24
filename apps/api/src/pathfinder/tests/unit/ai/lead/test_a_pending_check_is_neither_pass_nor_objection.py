"""A study step the site could not describe is a pending check: the verdict
names it, and no reader counts the turn as verified."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM, EDA_DATASET_ID_PARAM

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead import turn_budget
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.contract_messages import blamed_the_site_message
from pathfinder.ai.lead.ledger import InvestigationLedger, blamed_the_site
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.analysis_kinds import unread_analyses
from pathfinder.tests._support.analysis_catalog import UNREADABLE_SEARCH
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead._analysis_thread import document
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state
from pathfinder.tests.unit.ai.lead.test_verify_dispatch_digest import (
    _BUILD_DIGEST,
    _kinase_deps,
    _session_with_step,
    _verify,
)

pytestmark = pytest.mark.usefixtures("collector")


def _digest(*pending: str) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="61 genes; the check of step_de is pending.",
        reason="counts plausible",
        success=True,
        caveats=["The cut of step_de is pending: the site did not describe it."],
        pending_checks=list(pending),
    )


async def test_the_digest_takes_its_pending_checks_from_the_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the checker wrote there is replaced by what the graph holds."""
    session = _session_with_step(
        "plasmodb",
        name="DE",
        search_name="GenesByText",
        count=61,
        wdk_strategy_id=330558093,
    )
    graph = session.get_graph(None)
    assert graph is not None
    add_step_to_graph(
        graph,
        StrategyStep(
            id="step_de",
            kind=StepKind.SEARCH,
            search_name=UNREADABLE_SEARCH,
            parameters={
                EDA_DATASET_ID_PARAM: StringValue(value="DS_e973eadd57"),
                EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
            },
        ),
    )
    deps = _kinase_deps(session)
    deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330558093, root_count=61
    )
    written: dict[str, Any] = {
        "digest": {**_BUILD_DIGEST["digest"], "pendingChecks": ["step_made_up"]}
    }

    delta = await _verify(monkeypatch, deps, written)

    assert (delta.digest.success, delta.digest.pending_checks) == (True, ["step_de"])
    assert deps.state.turn_markers.verified is False


async def test_a_strategy_with_every_study_step_read_has_no_pending_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _kinase_deps(
        _session_with_step(
            "plasmodb",
            name="Kinases",
            search_name="GenesByText",
            count=61,
            wdk_strategy_id=330558093,
        )
    )
    deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330558093, root_count=61
    )

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert (delta.digest.pending_checks, deps.state.turn_markers.verified) == (
        [],
        True,
    )


def test_the_ledger_says_passed_with_the_pending_check() -> None:
    rendered = render_verification_full(VerificationSection(digest=_digest("step_de")))

    lines = rendered.splitlines()
    assert "- verdict: passed, 1 check pending: step_de" in lines
    assert "- success: True" not in lines


def test_the_budget_verdict_names_the_pending_check() -> None:
    assert turn_budget._verdict(_digest("step_de")) == (
        "Verification passed, 1 check pending: step_de."
    )
    assert turn_budget._verdict(_digest()) == "Verification passed."


def test_a_pass_with_a_pending_check_has_not_passed() -> None:
    assert (_digest("step_de").passed, _digest().passed) == (False, True)


def test_passed_is_not_part_of_the_digest_schema() -> None:
    """The wire carries success and the pending list; passed is read from both."""
    assert "passed" not in _digest("step_de").model_dump(by_alias=True)


def _graph_with_an_unread_step() -> StrategyGraph:
    graph = StrategyGraph("g1", "DE", "plasmodb")
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(
            id="step_de",
            kind=StepKind.SEARCH,
            search_name=UNREADABLE_SEARCH,
            parameters={
                EDA_DATASET_ID_PARAM: StringValue(value="DS_e973eadd57"),
                EDA_ANALYSIS_SPEC_PARAM: document("18h", 0.05),
            },
        ),
    )
    return graph


def test_a_kind_stamped_later_keeps_the_stored_pending_list() -> None:
    """The check of that step has still not run, so the stored verdict stands."""
    graph = _graph_with_an_unread_step()
    state = pipeline_state(user_prompt="DE genes at 18h")
    state.user_message_id = uuid4()
    judged = live_tree(graph)
    state.domain.answered_graph = judged
    state.domain.record_verdict(_digest("step_de"), revision=strategy_revision(judged))
    unread_before = unread_analyses(graph)

    graph.note_analysis_kinds(
        {
            "step_de": StampedKind(
                search_name=UNREADABLE_SEARCH, kind=AnalysisKind.COMPUTE
            )
        }
    )
    state.domain.answered_graph = live_tree(graph)
    state.user_message_id = uuid4()
    verdict = state.turn_verdict

    assert (unread_before, unread_analyses(graph)) == (["step_de"], [])
    assert strategy_revision(judged) == strategy_revision(live_tree(graph))
    assert verdict is not None
    assert verdict.pending_checks == ["step_de"]


def test_the_compact_ledger_names_the_pending_check() -> None:
    ledger = InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(),
        verification=VerificationSection(digest=_digest("step_de")),
    )

    lines = ledger.render_summary().splitlines()
    assert ledger.verification.successful is False
    assert "- successful: False" in lines
    assert "- pending_checks: step_de" in lines


def test_the_compact_ledger_has_no_pending_line_without_one() -> None:
    ledger = InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(),
        verification=VerificationSection(digest=_digest()),
    )

    lines = ledger.render_summary().splitlines()
    assert "- successful: True" in lines
    assert [line for line in lines if "pending" in line] == []


_PENDING_REPLIES = {
    "temporarily": (
        "VEuPathDB's search catalog was temporarily unreadable, so the "
        "check of the DE step is pending."
    ),
    "again later": (
        "The site did not describe the DE step's analysis; I will read it "
        "again later, and until then its check is pending."
    ),
}


def test_a_reply_about_a_pending_check_is_not_site_blame() -> None:
    """The site did not describe the step, so naming the site is the truth."""
    clean = BuildSection(
        outcome=BuildOutcome(pushed_step_ids=["step_de"], root_count=61)
    )
    pending = VerificationSection(digest=_digest("step_de"))

    got = {
        name: blamed_the_site(text, build=clean, verification=pending)
        for name, text in _PENDING_REPLIES.items()
    }

    assert got == {"temporarily": None, "again later": None}


def test_the_same_reply_without_a_pending_check_is_site_blame() -> None:
    clean = BuildSection(
        outcome=BuildOutcome(pushed_step_ids=["step_de"], root_count=61)
    )
    passed = VerificationSection(digest=_digest())

    got = {
        name: blamed_the_site(text, build=clean, verification=passed)
        for name, text in _PENDING_REPLIES.items()
    }

    assert got == {
        "temporarily": "it names 'veupathdb' together with 'temporarily'",
        "again later": "it names 'the site' together with 'again later'",
    }


_BUSY = "VEuPathDB is temporarily busy, so try the build again later."


def _clean_build() -> BuildSection:
    return BuildSection(
        outcome=BuildOutcome(pushed_step_ids=["step_de"], root_count=61)
    )


def test_a_busy_site_is_blame_even_with_a_pending_check() -> None:
    """Only the sentence about the pending step is exempt, not the reply."""
    pending = VerificationSection(digest=_digest("step_de"))

    assert blamed_the_site(_BUSY, build=_clean_build(), verification=pending) == (
        "it names 'veupathdb' together with 'busy'"
    )


def test_a_reply_with_both_sentences_is_refused_for_the_busy_one() -> None:
    pending = VerificationSection(digest=_digest("step_de"))
    reply = (
        f"{_PENDING_REPLIES['temporarily']} {_PENDING_REPLIES['again later']} {_BUSY}"
    )

    blame = blamed_the_site(reply, build=_clean_build(), verification=pending)

    assert blame == "it names 'veupathdb' together with 'busy'"
    correction = blamed_the_site_message(blame, None)
    assert "(it names 'veupathdb' together with 'busy')" in correction


def test_a_site_sentence_naming_the_pending_step_is_exempt() -> None:
    pending = VerificationSection(digest=_digest("step_de"))
    reply = "The site will refresh step_de's analysis later; its check is pending."

    got = {
        "step_de": blamed_the_site(reply, build=_clean_build(), verification=pending)
    }

    assert got == {"step_de": None}
