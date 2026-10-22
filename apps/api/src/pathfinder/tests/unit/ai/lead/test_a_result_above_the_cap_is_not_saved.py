from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.turn_facts import SavedSetFact, TurnFacts, UnsavedSetFact
from pathfinder.platform.config import get_settings
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

CAP = get_settings().step_genes_cap
ROOT_WDK_STEP = 227_284_190
SINGLETON_PROTEINS = 523_795


def _session(site_id: str, record_type: str, count: int) -> StrategySession:
    session = session_with_one_step(site_id, step_id="step_root")
    assert session.graph is not None
    session.graph.record_type = record_type
    session.sync_state = WDKSyncState(
        step_counts={"step_root": count},
        wdk_step_ids={"step_root": ROOT_WDK_STEP},
        wdk_strategy_id=214_645_070,
    )
    return session


def _facts(
    session: StrategySession,
    *,
    wrote: bool = True,
    saved: tuple[CreatedGeneSet, ...] = (),
) -> TurnFacts:
    deps = lead_deps(
        pipeline_state(session.site_id, user_prompt="singleton proteins"),
        strategy_session=session,
    )
    deps.state.turn_markers.edited = wrote
    for created in saved:
        deps.state.turn_markers.record_gene_set(created)
    return turn_facts(deps)


@pytest.mark.parametrize(
    ("site_id", "record_type", "noun"),
    [("plasmodb", "transcript", "gene"), ("orthomcl", "sequence", "protein")],
)
def test_a_root_above_the_cap_says_the_result_was_not_saved(
    site_id: str, record_type: str, noun: str
) -> None:
    facts = _facts(_session(site_id, record_type, SINGLETON_PROTEINS))

    assert facts.unsaved == UnsavedSetFact(
        count=SINGLETON_PROTEINS, cap=CAP, record_noun=noun
    )


def test_the_sentence_counts_the_result_in_its_own_records_on_orthomcl() -> None:
    facts = _facts(_session("orthomcl", "sequence", SINGLETON_PROTEINS))

    assert facts.unsaved is not None
    assert facts.unsaved.sentence == (
        f"The result was not saved as a gene set: it holds 523,795 proteins, "
        f"more than the {CAP:,} a gene set holds"
    )


@pytest.mark.parametrize(
    ("site_id", "record_type", "count", "wrote"),
    [
        ("orthomcl", "group", SINGLETON_PROTEINS, True),
        ("orthomcl", "sequence", CAP, True),
        ("orthomcl", "sequence", SINGLETON_PROTEINS, False),
    ],
)
def test_no_fact_for_groups_a_root_within_the_cap_or_a_turn_that_wrote_nothing(
    site_id: str, record_type: str, count: int, *, wrote: bool
) -> None:
    facts = _facts(_session(site_id, record_type, count), wrote=wrote)

    assert (facts.unsaved, facts.text().count("not saved as a gene set")) == (None, 0)


def test_a_root_above_the_cap_after_an_in_place_edit_is_not_saved() -> None:
    saved_before_the_edit = CreatedGeneSet(
        id="gs-1", name="singletons", gene_count=4593, record_type="sequence"
    )

    facts = _facts(
        _session("orthomcl", "sequence", SINGLETON_PROTEINS),
        saved=(saved_before_the_edit,),
    )

    assert (facts.unsaved, facts.saved) == (
        UnsavedSetFact(count=SINGLETON_PROTEINS, cap=CAP, record_noun="protein"),
        [
            SavedSetFact(
                kind="gene_set", name="singletons", count=4593, record_noun="protein"
            )
        ],
    )


def test_a_set_saved_from_another_step_leaves_the_result_unsaved() -> None:
    narrower = CreatedGeneSet(id="gs-2", name="3D7 singletons", gene_count=812)

    facts = _facts(
        _session("orthomcl", "sequence", SINGLETON_PROTEINS), saved=(narrower,)
    )

    assert facts.unsaved == UnsavedSetFact(
        count=SINGLETON_PROTEINS, cap=CAP, record_noun="protein"
    )
    assert [s.name for s in facts.saved] == ["3D7 singletons"]
