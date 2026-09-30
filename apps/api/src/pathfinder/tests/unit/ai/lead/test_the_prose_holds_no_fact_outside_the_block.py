"""The reply explains, recommends and asks: it prints no number and no
identifier the facts part does not show, and no link the facts part does not hold."""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.contract_messages import fact_outside_the_block_message
from pathfinder.ai.lead.facts_in_prose import outside_the_facts
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import RECORD_WORDS
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_URL = "https://plasmodb.org/plasmo/app/workspace/strategies/440299573/440299574"
_FACTS = (
    "GO Term: 288 genes\nGO term: GO:0031225 (anchored component of membrane)\n"
    f"Organism: Plasmodium falciparum 3D7\n{_URL}"
)


def test_a_count_the_facts_show_is_a_fact_inside_the_block() -> None:
    assert outside_the_facts("The strategy returns **288** genes.", _FACTS, ()) == []


def test_a_count_the_facts_do_not_show_is_printed_outside_them() -> None:
    assert outside_the_facts("The strategy returns 289 genes.", _FACTS, ()) == ["289"]


def test_a_count_is_held_whatever_its_thousands_separator() -> None:
    facts = "Transmembrane Domain Count: 1,183 genes"

    assert outside_the_facts("It keeps 1183 genes, 1,183 in all.", facts, ()) == []


def test_a_separator_out_of_its_place_writes_another_number() -> None:
    facts = "Result: 2,160 genes"

    assert outside_the_facts("It held 21,60 or 2,1600 genes.", facts, ()) == [
        "21,60",
        "2,1600",
    ]


def test_a_product_name_the_facts_show_may_be_named() -> None:
    facts = "Sampled products: Cortexin-1, A2"

    assert outside_the_facts("Cortexin-1 and A2 lead the list.", facts, ()) == []
    assert outside_the_facts("Cortexin-2 and A3 lead the list.", facts, ()) == [
        "Cortexin-2"
    ]


@pytest.mark.parametrize(
    ("prose", "printed"),
    [
        ("It returns a 36-gene set.", []),
        ("It returns a 37-gene set.", ["37-gene"]),
        ("The 6-restricted genes stay.", []),
        ("The cut is the 95th percentile.", []),
        ("The cut is the 90th percentile.", ["90th"]),
        ("The cut is 1.5-fold.", []),
        ("Three are surface protease GP63.", ["Three"]),
        ("The strain is SC5314, the organism 3D7.", []),
        ("AGAP009262 is its ortholog.", ["AGAP009262"]),
        ("Tb927.10.1234 is in the result.", ["Tb927.10.1234"]),
    ],
)
def test_a_number_with_a_suffix_is_the_number_and_an_identifier_has_its_shape(
    prose: str, printed: list[str]
) -> None:
    facts = "Result: 36 genes\nChromosome: 6\nMinimum percentile: 95\nFold: 1.5"

    assert outside_the_facts(prose, facts, ()) == printed


def test_a_number_the_facts_show_with_a_unit_is_held() -> None:
    facts = "1.5 on the log2 scale is 2.83-fold"

    assert outside_the_facts("That is 2.83 on the fold scale.", facts, ()) == []


def test_a_term_the_facts_show_may_be_named() -> None:
    prose = "The GO:0031225 term holds the anchored proteins of Plasmodium 3D7."

    assert outside_the_facts(prose, _FACTS, ()) == []


def test_an_identifier_the_facts_do_not_show_is_printed_outside_them() -> None:
    prose = "I wrote step_1a2b3c4d with edit_strategy on PF3D7_1133400 and hsap:N."

    assert outside_the_facts(prose, _FACTS, ()) == [
        "step_1a2b3c4d",
        "edit_strategy",
        "PF3D7_1133400",
        "hsap:N",
    ]


def test_a_search_url_segment_is_printed_outside_the_facts() -> None:
    prose = "The GenesByGoTerm search reads the term."

    assert outside_the_facts(prose, _FACTS, {"GenesByGoTerm"}) == ["GenesByGoTerm"]


def test_a_link_the_facts_hold_may_be_given_and_no_other() -> None:
    prose = (
        f"Open [the strategy]({_URL}) on the site, or read "
        "https://plasmodb.org/plasmo/app/strategy/1 instead."
    )

    assert outside_the_facts(prose, _FACTS, ()) == [
        "https://plasmodb.org/plasmo/app/strategy/1"
    ]


def test_an_ordered_list_s_item_numbers_are_no_numbers() -> None:
    prose = "Two choices:\n1. keep the default\n2. widen the cutoff"

    assert outside_the_facts(prose, _FACTS, ()) == []


def test_plain_words_and_site_names_are_prose() -> None:
    prose = "PlasmoDB holds the anchored proteins; I recommend the wider cutoff."

    assert outside_the_facts(prose, _FACTS, ()) == []


_HELD = (
    f"{_FACTS}\nTransmembrane domains: 2-99\nGene ID: PF3D7_0102300\n"
    "Profile pattern: hsap:3\nIncluded species: tgon, pfal\nP-value cutoff: 0.05"
)


@pytest.mark.parametrize(
    ("prose", "printed"),
    [
        ("About 80% of them carry the domain.", ["80%"]),
        ("The cutoff stays at 0.05 here.", []),
        ("The cutoff stays at 0.01 here.", ["0.01"]),
        ("It keeps 2-99 domains.", []),
        ("It keeps 2 to 99 domains.", ["2", "99"]),
        ("The site built it in 2026.", ["2026"]),
        ("It keeps roughly 1,234 of them.", ["1,234"]),
        ("PF3D7_0102300 is in the result.", []),
        ("PF3D7_9999999 is in the result.", ["PF3D7_9999999"]),
        ("The pattern hsap:3 stays.", []),
        ("The pattern hsap:4 stays.", ["hsap:4"]),
        ("The species tgon and pfal stay.", []),
        ("One step, then two more.", []),
        ("It ran three checks.", ["three"]),
        (
            "Read [the strategy](https://plasmodb.org/plasmo/app/strategy/1).",
            ["https://plasmodb.org/plasmo/app/strategy/1"],
        ),
        ("The `step_3` step reads it.", ["step_3"]),
        (f"Open {_URL}.", []),
    ],
)
def test_a_printed_fact_is_refused_and_a_shown_identifier_is_not(
    prose: str, printed: list[str]
) -> None:
    assert outside_the_facts(prose, _HELD, ()) == printed


def _built_turn() -> LeadDeps:
    graph = StrategyGraph(graph_id="g1", name="Anchored", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id="c_go", search_name="GenesByGoTerm"))
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={"c_go": 288})
    spec = OperationalSpec(
        goal="anchored proteins",
        criteria=[
            Criterion(
                id="c_go",
                text="GPI anchored",
                search_name="GenesByGoTerm",
                search_display_name="GO Term",
                resolved_params=bound({"GoTerm": StringValue(value="GO:0031225")}),
            )
        ],
    )
    state = pipeline_state(
        user_prompt="GPI-anchored proteins.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.record_build(BuildOutcome(pushed_step_ids=["c_go"]))
    state.turn_markers.verified = True
    return lead_deps(state, strategy_session=session)


def test_the_contract_refuses_an_unshown_count_and_names_it() -> None:
    deps = _built_turn()
    report = reply(
        "The strategy returns 288 of 300 genes from the GenesByGoTerm search.",
        changed=True,
    )
    found = reconcile(report, turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in found] == [
        (
            "fact_outside_the_block",
            fact_outside_the_block_message(["300", "GenesByGoTerm"]),
        )
    ]


def test_a_reply_that_points_at_the_facts_stands() -> None:
    deps = _built_turn()
    report = reply(
        "The GO:0031225 step holds the anchored proteins; its count is shown "
        "beside this reply. I recommend checking it against your controls.",
        changed=True,
    )

    assert [m.kind for m in reconcile(report, turn_record(run_context_for(deps)))] == []


def test_the_correction_says_the_conversation_s_facts_stand_beside_the_replies() -> (
    None
):
    assert fact_outside_the_block_message(["288"]) == (
        "Your reply prints ``288``, and no fact holds it. The facts this "
        "conversation showed - each step with its values and count, the caveats "
        "and gaps, the link, the saved sets, the control results and the records "
        "this turn read - stand beside its replies, with the options this reply "
        "offers. A count a comparison of this turn returned, and the difference "
        "of two counts the facts show, are facts too. Take out only ``288`` and "
        "keep every other part of the reply as it is, every count the facts show "
        "included. Do not say where a fact is shown."
    )


# A T. b. gambiense record on chromosome 6, and a result of 37 genes.
_RECORD_HELD = (
    "Text search: 37 genes\n"
    "Read: Tbg972.6.590: https://tritrypdb.org/tritrypdb/app/record/gene/Tbg972.6.590\n"
    f"{RECORD_WORDS}hypothetical protein, T. brucei gambiense DAL972, chromosome 6"
)


@pytest.mark.parametrize(
    ("prose", "printed"),
    [
        ("Tbg972.6.590 sits on chromosome 6.", []),
        ("DAL972 adds 6 more genes.", ["6"]),
        ("The search keeps 37 genes.", []),
    ],
)
def test_a_number_of_a_record_s_own_words_is_held_only_beside_its_word(
    prose: str, printed: list[str]
) -> None:
    assert outside_the_facts(prose, _RECORD_HELD, ()) == printed


# The C. neoformans comparison: the facts name the groups by their labels.
_GROUPS_HELD = "Reference group: WT input 30C\nCompared group: WT input 37C"


@pytest.mark.parametrize(
    ("prose", "printed"),
    [
        ("These are higher at 37°C than at 30°C.", []),
        ("These are higher at 37C than at 30C.", []),
        ("These are higher at 39°C than at 30°C.", ["39"]),
    ],
)
def test_a_number_glued_to_its_unit_is_read_as_the_number(
    prose: str, printed: list[str]
) -> None:
    assert outside_the_facts(prose, _GROUPS_HELD, ()) == printed


def test_a_spelled_number_is_read_as_its_digits() -> None:
    held = "Read 8 records"

    assert outside_the_facts("Verification sampled eight records.", held, ()) == []
    assert outside_the_facts("Verification sampled nine records.", held, ()) == ["nine"]


# The typed facts a row shows, each written the way a reply may restate it.
_TYPED_HELD = (
    "Result: 1,234,567 genes\n"
    "Minimum percentile: 95\n"
    "Significance threshold: 1e-05\n"
    "Effect size threshold at the chosen 1: 8 of 7,884 genes tested; at 0: 41"
)


@pytest.mark.parametrize(
    "prose",
    [
        "It returns 1234567 genes, 1,234,567 in all.",
        "Genes above the 95th percentile.",
        "Genes at p < 1e-05.",
        "Genes at p < 1e-5.",
        "Genes at p < 1E-05.",
        "Genes at p < 0.00001.",
        "8 of the 7884 genes tested pass the cut.",
    ],
)
def test_a_typed_fact_is_held_however_the_reply_writes_it(prose: str) -> None:
    assert outside_the_facts(prose, _TYPED_HELD, ()) == []


def test_another_number_in_scientific_notation_is_printed_outside_the_facts() -> None:
    assert outside_the_facts("Genes at p < 1e-6.", _TYPED_HELD, ()) == ["1e-6"]
