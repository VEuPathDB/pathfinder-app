"""FRAME is sent back, once per pass, to ask which presence a request over many
genomes means, unless the request names genomes or a reading was accepted."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import PhyleticTree, StringValue

from pathfinder.ai.agents import frame_result_checks
from pathfinder.ai.agents.frame_result_checks import (
    hold_an_every_genome_presence_to_a_question,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.readings import AcceptedReading
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

TREE = recorded_ortho_taxonomy()
PLAS = "+".join(labelled_genomes(TREE, "Plasmodium "))
TOXO = "+".join(labelled_genomes(TREE, "Toxoplasma "))
EVERY = f"{PLAS}=61T AND {TOXO}=0T"
ASKED = (
    "Which ortholog groups are present in all Plasmodium species but absent from "
    "Toxoplasma gondii?"
)
SINGLE = (
    "List the ortholog groups that have exactly one protein in every apicomplexan "
    "genome."
)


class _Taxonomy:
    def __init__(self) -> None:
        self.read: list[str] = []

    async def __call__(self, site_id: str) -> PhyleticTree | None:
        self.read.append(site_id)
        return TREE


@pytest.fixture
def taxonomy(monkeypatch: pytest.MonkeyPatch) -> _Taxonomy:
    held = _Taxonomy()
    monkeypatch.setattr(frame_result_checks, "ortho_taxonomy", held)
    return held


def _criterion(
    search: str, params: dict[str, str], reading: AcceptedReading | None = None
) -> Criterion:
    return Criterion(
        id="c_groups",
        text="the groups the request asks for",
        search_name=search,
        resolved_params={
            name: BoundValue(value=StringValue(value=value), source="chosen")
            for name, value in params.items()
        },
        accepted_reading=reading,
    )


def _context(
    criterion: Criterion, message: str, *, site_id: str = "orthomcl"
) -> RunContext[AgentDeps]:
    ctx = agent_run_context(site_id=site_id)
    ctx.deps.agent_state.operational_spec_draft.criteria = [criterion]
    ctx.deps.agent_state.request_messages = [message]
    return ctx


def _expression(text: str) -> Criterion:
    return _criterion("GroupsByPhyleticPattern", {"phyletic_expression": text})


async def test_every_plasmodium_genome_is_sent_back_twice_for_a_question(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression(EVERY), ASKED)
    result = FrameResult(summary="Bound.")

    with pytest.raises(ModelRetry) as sent_back:
        await hold_an_every_genome_presence_to_a_question(ctx, result)

    told = str(sent_back.value)
    assert "61 genomes of 23 species" in told
    assert "Plasmodium falciparum 20" in told
    assert "at least 55 of the 61 genomes" in told
    assert "every one of the 23 species" in told
    assert "Absence binds without a question." in told
    assert told.count("Ask one question") == 1
    assert "three readings" in told
    with pytest.raises(ModelRetry):
        await hold_an_every_genome_presence_to_a_question(ctx, result)
    assert await hold_an_every_genome_presence_to_a_question(
        ctx, result
    ) == result.with_gap(
        "every_genome_unasked",
        "c_groups binds presence in every genome of a list, and the researcher "
        "was not asked which presence the request means.",
    )
    assert taxonomy.read == ["orthomcl", "orthomcl", "orthomcl"]


async def test_single_copy_over_a_clade_binds_as_written(taxonomy: _Taxonomy) -> None:
    ctx = _context(_expression("APIC=139T AND APIC=139"), ASKED)
    result = FrameResult(summary="Bound.")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result


async def test_a_request_that_names_genomes_binds_as_written(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression("APIC=139T"), SINGLE)
    result = FrameResult(summary="Bound.")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result


async def test_an_accepted_reading_binds_as_written(taxonomy: _Taxonomy) -> None:
    reading = AcceptedReading(
        reading="Every one of the 61 genomes", params={"phyletic_expression": EVERY}
    )
    ctx = _context(
        _criterion("GroupsByPhyleticPattern", {"phyletic_expression": EVERY}, reading),
        ASKED,
    )
    result = FrameResult(summary="Bound.")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result
    assert taxonomy.read == []


async def test_a_genomics_site_draft_reads_no_taxonomy(taxonomy: _Taxonomy) -> None:
    ctx = _context(
        _criterion("GenesByMolecularWeight", {"min_molecular_weight": "10000"}),
        ASKED,
        site_id="plasmodb",
    )
    result = FrameResult(summary="Bound.")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result
    assert taxonomy.read == []


async def test_a_pass_that_asks_already_is_not_sent_back(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression(EVERY), ASKED)
    result = FrameResult(summary="Asked.", disposition="needs_user")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result
    assert taxonomy.read == []


async def test_three_single_genome_species_ask_nothing(taxonomy: _Taxonomy) -> None:
    ctx = _context(_expression("pfal+pviv+tgon=3T"), ASKED)
    result = FrameResult(summary="Bound.")

    assert await hold_an_every_genome_presence_to_a_question(ctx, result) is result


async def test_only_the_readings_that_differ_are_asked(taxonomy: _Taxonomy) -> None:
    ctx = _context(_expression("pfal+pfag+pviv=3T"), ASKED)

    with pytest.raises(ModelRetry) as sent_back:
        await hold_an_every_genome_presence_to_a_question(
            ctx, FrameResult(summary="Bound.")
        )

    told = str(sent_back.value)
    assert "3 genomes of 2 species; Plasmodium falciparum 2" in told
    assert "two readings" in told
    assert "every one of the 3 genomes (recommended)" in told
    assert "every one of the 2 species" in told
    assert "percent" not in told


async def test_two_lists_in_one_criterion_make_one_question(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression(f"{PLAS}=61T AND {TOXO}=15T"), ASKED)

    with pytest.raises(ModelRetry) as sent_back:
        await hold_an_every_genome_presence_to_a_question(
            ctx, FrameResult(summary="Bound.")
        )

    told = str(sent_back.value)
    assert told.count("Ask one question") == 1
    assert "61 genomes of 23 species" in told
    assert "15 genomes of 1 species; Toxoplasma gondii 15" in told
    assert "at least 55 of the 61 genomes and at least 14 of the 15 genomes" in told


async def test_a_clade_of_single_genome_species_offers_no_species_reading(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression("MAMM=18T"), ASKED)

    with pytest.raises(ModelRetry) as sent_back:
        await hold_an_every_genome_presence_to_a_question(
            ctx, FrameResult(summary="Bound.")
        )

    told = str(sent_back.value)
    assert "two readings" in told
    assert "at least 17 of the 18 genomes (90 percent)" in told
    assert "species present" not in told


async def test_the_question_asked_for_names_the_keys_its_readings_approximate(
    taxonomy: _Taxonomy,
) -> None:
    ctx = _context(_expression(EVERY), ASKED)
    ctx.deps.agent_state.stated_requirements = [
        Constraint(
            kind=ConstraintKind.OTHER,
            label="presence",
            requested_value="present in all Plasmodium species",
            source=ConstraintSource.USER_EXPLICIT,
        )
    ]

    with pytest.raises(ModelRetry) as sent_back:
        await hold_an_every_genome_presence_to_a_question(
            ctx, FrameResult(summary="Bound.")
        )

    assert (
        "Name in the question's `requirements` the keys of the requirements its "
        "readings approximate, from R1."
    ) in str(sent_back.value)
