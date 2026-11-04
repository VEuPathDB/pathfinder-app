from __future__ import annotations

from veupathdb.domain.parameters import ParamValue, StringValue

from pathfinder.ai.agents.frame_pick_checks import hold_an_unsettled_pick_to_a_question
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.recorded_cards import card_questions
from pathfinder.domain.strategy.genome_group import GenomeGroup
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.question_options import ReadGenomes
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_SEARCH = "GenesByOrthologPattern"
_GENOMES = tuple(f"g{n:02d}" for n in range(61))
_ONE = "At least one of 61 genomes (1,259 genes)"
_ALL = "All 61 genomes (501 genes)"
_ANY_READ = Measurement(kind="any_strain", param="included_species", count=1259)
_ALL_READ = Measurement(kind="all_strains", param="included_species", count=501)
_ANY_UNREAD = Measurement(kind="any_strain", param="included_species")
_ANY_EQUAL = Measurement(kind="any_strain", param="included_species", count=501)


def _profile(
    genomes: tuple[str, ...] = _GENOMES,
    measurements: tuple[Measurement, ...] = (_ANY_READ, _ALL_READ),
    *,
    search: str = _SEARCH,
    group: GenomeGroup | None = None,
) -> Criterion:
    tokens = "%".join(f"{code}:Y" for code in genomes)
    values: dict[str, ParamValue] = {
        "profile_pattern": StringValue(value=f"%{tokens}%"),
        "included_species": StringValue(value=", ".join(genomes)),
        "excluded_species": StringValue(value="n/a"),
    }
    return Criterion(
        id="c_profile",
        text="an ortholog in the listed genomes",
        search_name=search,
        record_class="transcript",
        role="seed",
        result_count=501,
        measurements=list(measurements),
        genome_group=group,
        resolved_params=bound(values),
    )


def _held(criterion: Criterion) -> tuple[FrameResult, list[OpenQuestion]]:
    ctx = agent_run_context(site_id="cryptodb")
    draft = OperationalSpec(
        goal="orthologs",
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )
    ctx.deps.agent_state.operational_spec_draft = draft
    held = hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="framed"))
    assert isinstance(held, FrameResult)
    return held, held.questions(ctx.deps.agent_state.operational_spec_draft)


def test_differing_counts_ask_once_with_both_numbers() -> None:
    held, questions = _held(_profile())

    [asked] = questions
    assert held.disposition == "needs_user"
    assert [o.label for o in asked.options] == [_ONE, _ALL]
    assert asked.criterion_id == "c_profile"
    assert [o.binding for o in asked.options] == [
        ReadGenomes(
            criterion_id="c_profile",
            group=GenomeGroup(reading="at_least_one", genomes=_GENOMES),
        ),
        ReadGenomes(
            criterion_id="c_profile",
            group=GenomeGroup(reading="all", genomes=_GENOMES),
        ),
    ]


def test_neither_option_is_recommended() -> None:
    _, asked = _held(_profile())

    [card] = card_questions(asked)
    assert [o.recommended for o in card.options] == [False, False]


def test_the_strict_binding_stays_while_it_waits() -> None:
    criterion = _profile()
    ctx = agent_run_context(site_id="cryptodb")
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        goal="orthologs",
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )

    hold_an_unsettled_pick_to_a_question(ctx, FrameResult(summary="framed"))

    [held] = ctx.deps.agent_state.operational_spec_draft.criteria
    assert held.param_values == criterion.param_values
    assert (held.result_count, held.genome_group) == (501, None)


def test_equal_counts_ask_nothing() -> None:
    held, asked = _held(_profile(measurements=(_ANY_EQUAL, _ALL_READ)))

    assert (held.disposition, asked) == ("spec_ready", [])


def test_one_required_genome_asks_nothing() -> None:
    held, asked = _held(_profile(("pfal",), measurements=()))

    assert (held.disposition, asked) == ("spec_ready", [])


def test_a_count_that_did_not_arrive_asks_with_no_number() -> None:
    _, questions = _held(_profile(measurements=(_ANY_UNREAD, _ALL_READ)))

    [asked] = questions
    assert [o.label for o in asked.options] == ["At least one of 61 genomes", _ALL]


def test_a_search_too_slow_to_read_asks_with_no_number() -> None:
    slow = Measurement(
        kind="not_measurable",
        param="included_species",
        reading="the site counts this search too slowly",
    )

    _, questions = _held(_profile(measurements=(slow,)))

    [asked] = questions
    assert [o.label for o in asked.options] == ["At least one of 61 genomes", _ALL]


def test_a_value_no_reading_measures_asks_nothing() -> None:
    held, asked = _held(_profile(measurements=()))

    assert (held.disposition, asked) == ("spec_ready", [])


def test_a_stated_reading_is_not_asked_again() -> None:
    held, asked = _held(_profile(group=GenomeGroup(reading="all", genomes=_GENOMES)))

    assert (held.disposition, asked) == ("spec_ready", [])


def test_a_rebind_of_the_group_keeps_the_stated_reading() -> None:
    group = GenomeGroup(reading="at_least_one", genomes=_GENOMES)
    state = agent_run_context(site_id="cryptodb").deps.agent_state
    state.frame_set_criterion(_profile(group=group))

    state.frame_set_criterion(_profile())

    assert [c.genome_group for c in state.operational_spec_draft.criteria] == [group]


def test_another_search_asks_nothing() -> None:
    held, asked = _held(_profile(search="GenesByText"))

    assert (held.disposition, asked) == ("spec_ready", [])


def test_the_input_schema_of_a_pass_is_unchanged() -> None:
    schema = str(FrameResult.model_json_schema())

    assert "typedOptions" not in schema
    assert "read_genomes" not in schema
