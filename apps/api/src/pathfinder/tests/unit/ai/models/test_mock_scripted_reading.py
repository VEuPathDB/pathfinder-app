"""The mock reads a turn's words as the intent its arc states, from the typed
state the turn opens on."""

from __future__ import annotations

import pytest

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import IntentClassification, NamedControls, UserIntent
from pathfinder.ai.models.mock.consult_arc import WITHDRAWN
from pathfinder.ai.models.mock.reading import scripted_intent
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.strategy.constraints import ConstraintKind, FoldChangeValue
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests._support.site_organisms import serve_recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SITES = ("plasmodb", "vectorbase")
NEW = IntentClassification.NEW_STRATEGY
EXTEND = IntentClassification.EXTEND_STRATEGY
EDIT = IntentClassification.EDIT_STRATEGY
QUESTION = IntentClassification.FOLLOW_UP_QUESTION

BUILDS = [
    "single",
    "intersect",
    "union",
    "minus",
    "go",
    "combined",
    "count-question",
    "second-build",
    "controls-test",
    "sweep",
    "organism-universe",
    "radio-off-domain",
    "text-beside-organism",
    "odorant-lookup",
    "muris-phrase",
]
EDIT_OR_BUILD = [
    "orthologs",
    "syntenic-orthologs",
    "round-trip",
    "zero-then-relax",
    "portal-only",
]
EDITS = [
    "edit-param",
    "add-step",
    "replace-subtree",
    "delete-step-card",
    "clear",
    "rename",
]
NEW_REQUESTS = [
    "cross-organism",
    "other-site-experiment",
    "frame-loop",
    "separation",
    "eda-compare",
    "eda-compare-no-step",
    "eda-other-site",
    "user-dataset-deseq",
]
QUESTIONS = [
    "proposal",
    "variants",
    "save-gene-set",
    "export",
    "recall-preference",
    "recall",
    "recap",
    "gene-question",
    "kinase-question",
    "impact",
    "echo",
    "read-again",
    "widen-card",
    "list-ids",
    "derived-count",
]
AUDITS = ["audit", "audit-plan", "audit-finding", "audit-investigation"]


def _state(site_id: str, said: str, *, framed: bool = False) -> PipelineState:
    state = pipeline_state(site_id, user_prompt=said)
    if framed:
        state.domain.operational_spec = OperationalSpec(goal="kinases")
    return state


def _read(
    arc: str, site_id: str = "plasmodb", *, framed: bool = False, said: str = "Do it"
) -> UserIntent:
    text = f"{said} [[arc:{arc}]]"
    return scripted_intent(_state(site_id, text, framed=framed), text)


def _constraints(intent: UserIntent) -> list[tuple[ConstraintKind, str]]:
    return [(c.kind, c.requested_value) for c in intent.explicit_constraints]


@pytest.mark.parametrize("arc", BUILDS)
def test_a_build_starts_a_request_on_a_thread_that_framed_none(arc: str) -> None:
    assert _read(arc).classification is NEW


@pytest.mark.parametrize("arc", [*BUILDS, "assent", "union-refused"])
def test_a_build_on_a_framed_thread_extends_it(arc: str) -> None:
    assert _read(arc, framed=True).classification is EXTEND


def test_an_assent_extends_the_strategy_on_any_thread() -> None:
    assert _read("assent").classification is EXTEND


@pytest.mark.parametrize("arc", EDIT_OR_BUILD)
def test_a_growth_edits_a_framed_thread_and_starts_one_else(arc: str) -> None:
    assert (_read(arc).classification, _read(arc, framed=True).classification) == (
        NEW,
        EDIT,
    )


@pytest.mark.parametrize("arc", EDITS)
def test_an_edit_arc_reads_an_edit(arc: str) -> None:
    assert _read(arc).classification is EDIT


@pytest.mark.parametrize("arc", NEW_REQUESTS)
def test_a_new_request_arc_reads_a_new_strategy(arc: str) -> None:
    assert _read(arc).classification is NEW


@pytest.mark.parametrize("arc", QUESTIONS)
def test_a_question_arc_reads_a_question(arc: str) -> None:
    assert _read(arc).classification is QUESTION


@pytest.mark.parametrize("arc", AUDITS)
def test_an_audit_arc_reads_an_audit(arc: str) -> None:
    assert _read(arc).classification is IntentClassification.GENE_MODEL_AUDIT


@pytest.mark.parametrize(
    ("arc", "expected"),
    [
        ("off-topic", IntentClassification.OFF_TOPIC),
        ("context", IntentClassification.CONTEXT_STATEMENT),
        ("remember", IntentClassification.MEMORY_REQUEST),
    ],
)
def test_a_prose_arc_reads_its_own_classification(
    arc: str, expected: IntentClassification
) -> None:
    assert _read(arc).classification is expected


def test_the_withdraw_arc_states_the_fold_change_no_search_states() -> None:
    intent = _read("withdraw")

    assert (intent.classification, _constraints(intent)) == (
        NEW,
        [(ConstraintKind.FOLD_CHANGE, WITHDRAWN)],
    )
    assert [c.value for c in intent.explicit_constraints] == [
        FoldChangeValue(cut=2, direction="up")
    ]


def test_the_consult_arc_asks_on_a_new_request() -> None:
    assert _read("consult").classification is NEW


@pytest.mark.parametrize("site_id", SITES)
def test_the_attached_list_is_read_as_the_positive_controls(site_id: str) -> None:
    ids = SiteValues.for_site(site_id).controls.positive_ids[:2]
    text = f"Use these.\nAttached gene-ID list from controls.csv: {', '.join(ids)}"

    intent = scripted_intent(_state(site_id, text), text)

    assert (intent.classification, intent.named_controls) == (
        NEW,
        NamedControls(positive_ids=ids),
    )


def test_a_count_comparison_reads_its_two_sides() -> None:
    intent = _read("count-comparison", framed=True)

    assert (intent.classification, intent.is_differential) == (QUESTION, True)
    assert intent.differential_sides == ["product field", "product and notes"]


def test_a_message_with_no_token_reads_the_newest_earlier_arc() -> None:
    state = _state("plasmodb", "And now?")
    state.domain.exchanges = [
        Exchange(said="Clear it [[arc:clear]]"),
        Exchange(said="Remember this [[arc:remember]]"),
        Exchange(said="Thanks"),
    ]

    assert (
        scripted_intent(state, "And now?").classification
        is IntentClassification.MEMORY_REQUEST
    )


def test_a_message_with_no_token_on_a_new_thread_reads_as_a_question() -> None:
    state = _state("plasmodb", "Hello")

    assert scripted_intent(state, "Hello").classification is QUESTION


@pytest.mark.parametrize("site_id", SITES)
async def test_a_split_organism_is_held_whole(
    site_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_recorded_organisms(monkeypatch)
    organism = SiteValues.for_site(site_id).organism
    binomial, strain = organism.rsplit(" ", 1)
    said = f"Find {organism} genes whose proteins have a predicted signal peptide."
    text = f"{said} [[arc:single]][[fault:organism-split]]"
    state = _state(site_id, text)
    split = scripted_intent(state, text)
    deps = lead_deps(state)

    held = await hold_the_intent(deps, split, said)

    assert _constraints(split) == [
        (ConstraintKind.ORGANISM, binomial),
        (ConstraintKind.UNTYPED, f"{strain} genes"),
    ]
    assert _constraints(held)[0] == (ConstraintKind.ORGANISM, organism)
    assert deps.intent == held
