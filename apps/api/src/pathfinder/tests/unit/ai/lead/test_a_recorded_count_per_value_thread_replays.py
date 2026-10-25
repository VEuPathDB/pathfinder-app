"""The recorded orthomcl thread replayed through the tools: a tally of a leaf is
no answer about the result, the hint for a token of a multi-pick names no value
reference, the taxonomy step keeps the organism requirement grounded, and the
Lead's own reading card is asked with the readings the pass named."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import ConsultOption
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.frame_requirements import requirements_no_search_states
from pathfinder.ai.lead.lead_consult import refuse_a_card_that_binds_nothing
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.tools.standalone import step_tally
from pathfinder.ai.tools.standalone.step_tally import count_step_by_column
from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.reply_references import prose_faults
from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.experiment.column_tally import ColumnTally
from pathfinder.services.experiment.step_tally import CountedStep
from pathfinder.services.experiment.tally_rows import TallyRow
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    domain_answering,
    lead_deps,
    pipeline_state,
    requirement,
)

_GROUPS, _PROTEINS, _TAXA, _ROOT = 227288250, 227288260, 227288270, 227288280
_STRATEGY = 214647290
_TALLY_ID = "tally_57ea13f0"
_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism scope", "Plasmodium species")
_DEFINITION = requirement(
    ConstraintKind.OTHER,
    "singleton definition",
    "singleton genes, meaning genes in a group of their own",
)
_CODES = ["pfac", "pyxn", "pyyx", "pber", "pcoa"]
_LABELS = (
    "pfac (Plasmodium falciparum CD01), pyxn (Plasmodium yoelii yoelii 17XNL), "
    "pyyx (Plasmodium yoelii yoelii 17XNL 2023), pber (Plasmodium berghei ANKA), "
    "pcoa (Plasmodium coatneyi Hackeri)"
)


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="Which Plasmodium species has the most singleton genes, meaning genes "
        "in a group of their own?",
        constraints=[_ORGANISM, _DEFINITION],
        criteria=[
            Criterion(
                id="step_c3186ea7",
                text="Ortholog groups containing exactly one protein overall",
                search_name="GroupsBySequenceCount",
                search_display_name="Number of Sequences",
                resolved_params={
                    "all_count": BoundValue(
                        value=StringValue(value='{"min": 1.0, "max": 1.0}'),
                        source="chosen",
                    )
                },
                result_count=523795,
            ),
            Criterion(
                id="step_145443fa",
                text="Convert the groups into their proteins",
                search_name="FromGroups",
                search_display_name="Transform Groups to Proteins",
                result_count=523795,
            ),
            Criterion(
                id="step_5ebea5e6",
                text="Proteins from Plasmodium taxa",
                search_name="ByTaxonomy",
                search_display_name="Taxonomy",
                resolved_params={
                    "taxon_type_ahead": BoundValue(
                        value=MultiPickValue(values=_CODES),
                        source="chosen",
                        label=_LABELS,
                        display_name="Taxon",
                    )
                },
                result_count=333932,
            ),
        ],
    )


def _session() -> StrategySession:
    graph = StrategyGraph("g1", "Plasmodium singleton-gene strategy", "orthomcl")
    graph.record_type = "sequence"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_bd503b89",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_145443fa",
                search_name="FromGroups",
                primary_input=StrategyStepNode(
                    id="step_c3186ea7", search_name="GroupsBySequenceCount"
                ),
            ),
            secondary_input=StrategyStepNode(
                id="step_5ebea5e6", search_name="ByTaxonomy"
            ),
        )
    )
    graph.steps["step_c3186ea7"].record_class = "group"
    for step in ("step_145443fa", "step_5ebea5e6", "step_bd503b89"):
        graph.steps[step].record_class = "sequence"
    graph.recompute_roots()
    session = StrategySession(site_id="orthomcl")
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={
            "step_c3186ea7": _GROUPS,
            "step_145443fa": _PROTEINS,
            "step_5ebea5e6": _TAXA,
            "step_bd503b89": _ROOT,
        },
        step_counts={
            "step_c3186ea7": 523795,
            "step_145443fa": 523795,
            "step_5ebea5e6": 333932,
            "step_bd503b89": 2744,
        },
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_ROOT),
    )
    return session


async def _recorded_tally(step: CountedStep, column: str, top: int) -> ColumnTally:
    del top
    taxa = step.wdk_step_id == _TAXA
    return ColumnTally(
        id=_TALLY_ID if taxa else "tally_root",
        title="Proteins by Taxon Code",
        search_name=step.search_name,
        record_type=step.record_type,
        record_noun=step.record_noun,
        column=column,
        column_label="Taxon Code",
        total=333932 if taxa else 2744,
        distinct=61 if taxa else 0,
        rows=[
            TallyRow(value="pyxn", count=7666, label="Plasmodium yoelii yoelii 17XNL"),
            TallyRow(value="pova", count=6671, label="Plasmodium ovale curtisi GH01"),
        ]
        if taxa
        else [],
        site_id=step.site_id,
        step_url=step.step_url,
    )


@pytest.fixture(autouse=True)
def _counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(step_tally, "run_step_tally", _recorded_tally)


def _deps() -> LeadDeps:
    domain = domain_answering(_spec())
    domain.requirements = [_ORGANISM, _DEFINITION]
    state = pipeline_state(
        "orthomcl",
        user_prompt=_spec().goal,
        user_message_id=uuid4(),
        domain=domain,
    )
    return lead_deps(state, strategy_session=_session())


_FIRST_REPLY = (
    "Among the selected Plasmodium taxa, **Plasmodium yoelii yoelii 17XNL** has the "
    f"most singleton proteins: [tally:{_TALLY_ID}.pyxn]. The comparison covered "
    f"[tally:{_TALLY_ID}:values] taxon labels and [tally:{_TALLY_ID}] protein records "
    "in total. The strategy and its underlying counts are available here: [url]"
)


async def test_turn_one_tally_of_the_taxonomy_leaf_is_no_answer() -> None:
    deps = _deps()

    await count_step_by_column(run_context_for(deps), _TAXA, "abbreviation", 200)

    (fact,) = deps.state.turn_markers.tallies
    assert (fact.wdk_step_id, fact.result_step_id) == (_TAXA, _ROOT)
    faults = prose_faults(_FIRST_REPLY, turn_facts(deps))
    assert [(f.token, f.kind) for f in faults if f.kind == "tally_of_a_step"] == [
        (f"[tally:{_TALLY_ID}.pyxn]", "tally_of_a_step"),
        (f"[tally:{_TALLY_ID}:values]", "tally_of_a_step"),
        (f"[tally:{_TALLY_ID}]", "tally_of_a_step"),
    ]


async def test_turn_one_tally_of_the_root_is_the_answer() -> None:
    deps = _deps()

    await count_step_by_column(run_context_for(deps), _ROOT, "abbreviation", 200)

    (fact,) = deps.state.turn_markers.tallies
    assert (fact.wdk_step_id, fact.result_step_id) == (_ROOT, _ROOT)
    assert prose_faults("The result holds [tally:tally_root].", turn_facts(deps)) == []


async def test_turn_one_hint_names_no_reference_of_the_whole_taxon_list() -> None:
    deps = _deps()
    await count_step_by_column(run_context_for(deps), _TAXA, "abbreviation", 200)
    facts = turn_facts(deps)

    (taxon,) = facts.steps[2].parameters
    faults = [f for f in prose_faults(_FIRST_REPLY, facts) if f.token == "17XNL"]

    assert (taxon.name, taxon.picks) == ("taxon_type_ahead", 5)
    assert [(f.kind, f.references) for f in faults] == [
        ("listed_value", ("[value:step_5ebea5e6.taxon_type_ahead]",))
    ]
    message = unrendered_prose_message(faults)
    assert "write ``[value:step_5ebea5e6.taxon_type_ahead]``" not in message
    assert "cite it through a fact that holds it alone, or take it out." in message


_QUESTION = "Which Plasmodium species has the most singleton genes?"
_REVIEW = VerificationReview(
    requirements=[
        RequirementCheck(
            text="Plasmodium species",
            turn=1,
            how="search",
            status="met",
            answered_by=["step_5ebea5e6"],
        ),
        RequirementCheck(
            text="singleton genes, meaning genes in a group of their own",
            turn=1,
            how="search",
            status="met",
            answered_by=["step_c3186ea7"],
        ),
        RequirementCheck(text=_QUESTION, turn=1, how="analysis", status="unmet"),
    ]
)


def _checked() -> LeadDeps:
    deps = _deps()
    grounded = derive_ledger(deps.state, None).constraints.grounded
    gaps = check_gaps(structure=None, words=[], review=_REVIEW, requirements=grounded)
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.HANDOFF,
            prose="The final INTERSECT contains 2,744 records.",
            reason="A species-level count-and-ranking analysis is missing.",
            success=False,
            gaps=gaps,
            review=_REVIEW,
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


def test_turn_one_check_keeps_the_taxonomy_step_answering_the_organism() -> None:
    deps = _checked()

    assert deps.state.domain.verification_digest is not None
    assert deps.state.domain.verification_digest.gaps == [
        RequirementGap(text=_QUESTION, status="unmet")
    ]
    constraints = derive_ledger(deps.state, None).constraints
    assert [
        (g.constraint.requested_value, g.status)
        for g in constraints.grounded
        if g.constraint.source is ConstraintSource.USER_EXPLICIT
    ] == [
        ("Plasmodium species", ConstraintStatus.GROUNDED),
        (
            "singleton genes, meaning genes in a group of their own",
            ConstraintStatus.GROUNDED,
        ),
    ]
    assert (constraints.blocking, constraints.unmet_count) == (False, 0)


def test_turn_two_card_offers_no_drop_of_the_organism() -> None:
    assert requirements_no_search_states(_checked(), []) == []


_BUILT = (
    "ortholog groups present in at least one represented genome of every "
    "Plasmodium species"
)
_ALTERNATIVE = (
    "true species-level aggregation of singleton-gene counts across all strains"
)
_PROMPT = (
    "The site can answer which ortholog groups are present in at least one "
    "represented genome of every Plasmodium species. Should we use that reading, or "
    "require a true species-level aggregation of singleton-gene counts across all "
    "strains?"
)


def _turn_two_refusal(*labels: str) -> str:
    deps = _checked()
    deps.state.domain.name_reading(
        ChosenReading(chosen=_BUILT, alternatives=[_ALTERNATIVE])
    )
    card = CardQuestion(
        id="q1",
        prompt=_PROMPT,
        dimension=ConstraintKind.OTHER,
        options=[ConsultOption(label=label) for label in labels],
    )
    try:
        refuse_a_card_that_binds_nothing(
            run_context_for(deps, "call_card"), [card], reply="Choose a reading."
        )
    except ModelRetry as refused:
        return str(refused)
    return ""


def test_turn_two_leads_reading_card_is_asked_with_the_named_readings() -> None:
    assert _turn_two_refusal(_BUILT, _ALTERNATIVE) == ""


def test_turn_two_leads_own_labels_name_the_readings_and_no_recorded_card() -> None:
    refusal = _turn_two_refusal(
        "Use the represented-genome species-pattern reading",
        "Require true species-level aggregation",
    )

    assert "The card asks these as recorded, whatever the call writes: none." in (
        refusal
    )
    assert f"The readings the framing pass named offer: '{_BUILT}', " in refusal
    assert "No search on this site states" not in refusal
