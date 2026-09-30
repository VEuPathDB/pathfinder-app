"""A reply says who set a value as its facts row does, and writes a record's
product as the record writes it."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.lead.contract_messages import (
    altered_record_text_message,
    fact_outside_the_block_message,
    misattributed_source_message,
)
from pathfinder.ai.lead.facts_in_prose import (
    AlteredRecordText,
    MisattributedSource,
    altered_record_text,
    misattributed_source,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.turn_facts import ParameterFact, SourceFact, StepFact, TurnFacts
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# tritrypdb: the promastigote step, its 0 hr sample chosen and its biorep01
# experiment the site's default.
_PROMASTIGOTE = TurnFacts(
    steps=[
        StepFact(
            step_id="step_949602cf",
            display_name=(
                "L. infantum JPCM5 Promastigote-to-amastigote differentiation "
                "(L.d. Samples) Microarray (percentile)"
            ),
            count=569,
            parameters=[
                ParameterFact(
                    name="profileset_generic",
                    display_name="Experiment",
                    value="Linfantum promastigote time-course - biorep01",
                    label="Linfantum promastigote time-course - biorep01",
                    source="default",
                ),
                ParameterFact(
                    name="min_percentile",
                    display_name="Minimum expression percentile",
                    value="80",
                    source="default",
                ),
                ParameterFact(
                    name="samples_percentile_generic",
                    display_name="Samples",
                    value="0 hr",
                    label="0 hr",
                    source="chosen",
                ),
            ],
        )
    ]
)


def test_a_chosen_value_called_the_site_s_default_is_refused() -> None:
    prose = (
        "The promastigote evidence uses the site's default 0-hour sample from "
        "the biorep01 time-course profile."
    )

    assert misattributed_source(prose, _PROMASTIGOTE) == MisattributedSource(
        phrase="site's default 0-hour sample",
        claimed="default",
        shown=frozenset({"chosen"}),
    )


def test_a_value_called_by_the_source_its_row_shows_stands() -> None:
    replies = [
        "It uses the chosen 0-hour sample from the site's default biorep01 profile.",
        "The minimum percentile stays at the site's default of 80.",
        "The biorep01 profile is the site's default.",
        "The site's default settings apply elsewhere.",
    ]

    assert [misattributed_source(p, _PROMASTIGOTE) for p in replies] == [
        None,
        None,
        None,
        None,
    ]


def test_a_default_value_called_the_researcher_s_is_refused() -> None:
    found = misattributed_source("It keeps the 80 you asked for.", _PROMASTIGOTE)

    assert found == MisattributedSource(
        phrase="80 you asked for", claimed="stated", shown=frozenset({"default"})
    )


def test_the_refusal_names_the_phrase_and_the_row_s_source() -> None:
    message = misattributed_source_message(
        MisattributedSource(
            phrase="site's default 0-hour sample",
            claimed="default",
            shown=frozenset({"chosen"}),
        )
    )

    assert message == (
        "Your reply says ``site's default 0-hour sample``, and the facts row of "
        "that value shows it as chosen, not as the site's default. Say who set "
        "each value as its facts row does, and keep every other part of the reply "
        "as it is."
    )


# fungidb: two records the turn read from the lipase result.
_LIPASES = TurnFacts(
    sources=[
        SourceFact(
            url="https://fungidb.org/fungidb/app/record/gene/AN1675",
            record_id="AN1675",
            product="Putative lysophospholipase (phoshopholipase B)",
        ),
        SourceFact(
            url="https://fungidb.org/fungidb/app/record/gene/AN1799",
            record_id="AN1799",
            product=(
                "Ortholog(s) have lipase activity, role in lipid catabolic process "
                "and extracellular region localization"
            ),
        ),
    ]
)


def test_a_product_with_a_word_respelled_is_refused() -> None:
    prose = (
        "- **AN1675** - Putative lysophospholipase (phospholipase B).\n"
        "- **AN1799** - Orthologs have lipase activity, a role in lipid "
        "catabolic process."
    )

    assert altered_record_text(prose, _LIPASES) == [
        AlteredRecordText(
            record_id="AN1675",
            written="phospholipase",
            recorded="phoshopholipase",
        ),
        AlteredRecordText(
            record_id="AN1799", written="Orthologs", recorded="Ortholog(s)"
        ),
    ]


def test_a_product_copied_as_the_record_writes_it_stands() -> None:
    prose = (
        "AN1675 is a putative lysophospholipase (phoshopholipase B), and AN1799's "
        "Ortholog(s) have lipase activity. Both are phospholipases in the broad sense."
    )

    assert altered_record_text(prose, _LIPASES) == []


def test_the_record_text_refusal_quotes_the_record() -> None:
    message = altered_record_text_message(
        [
            AlteredRecordText(
                record_id="AN1675",
                written="phospholipase",
                recorded="phoshopholipase",
            )
        ]
    )

    assert message == (
        "Your reply writes ``phospholipase`` where the record of AN1675 writes "
        "``phoshopholipase``. A record's text is the site's: copy it as the record "
        "writes it or leave it out, and keep every other part of the reply as it is."
    )


def _read_turn() -> LeadDeps:
    """fungidb: the lipase result, and the record of AN1675 this turn read."""
    deps = lead_deps(pipeline_state("fungidb"))
    deps.state.turn_markers.record_read(
        ReadRecord(
            record_id="AN1675",
            url="https://fungidb.org/fungidb/app/record/gene/AN1675",
            product="Putative lysophospholipase (phoshopholipase B)",
            organism="Aspergillus nidulans FGSC A4",
        )
    )
    return deps


def test_the_turn_refuses_a_number_then_a_source_then_a_record_s_text() -> None:
    record = turn_record(run_context_for(_read_turn()))

    assert [
        record.prose_refusal(prose, [])
        for prose in (
            "AN1675 is a putative lysophospholipase (phoshopholipase B).",
            "AN1675 is a putative lysophospholipase (phospholipase B).",
            "AN1675 is one of 12 lipases.",
        )
    ] == [
        None,
        altered_record_text_message(
            [
                AlteredRecordText(
                    record_id="AN1675",
                    written="phospholipase",
                    recorded="phoshopholipase",
                )
            ]
        ),
        fact_outside_the_block_message(["12"]),
    ]


def test_the_turn_refuses_a_source_its_row_does_not_show() -> None:
    criterion = Criterion(
        id="c_promastigote",
        text="expressed in promastigotes",
        search_name="GenesByMicroarraylinfJPCM5",
        resolved_params={
            "samples_percentile_generic": BoundValue(
                value=MultiPickValue(values=["0 hr"]), source="chosen"
            )
        },
        param_display_names={"samples_percentile_generic": "Samples"},
    )
    state = pipeline_state(
        "tritrypdb",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion])
        ),
    )
    record = turn_record(run_context_for(lead_deps(state)))
    prose = "It uses the site's default 0-hour sample."

    assert record.prose_refusal(prose, []) == misattributed_source_message(
        MisattributedSource(
            phrase="site's default 0-hour sample",
            claimed="default",
            shown=frozenset({"chosen"}),
        )
    )
