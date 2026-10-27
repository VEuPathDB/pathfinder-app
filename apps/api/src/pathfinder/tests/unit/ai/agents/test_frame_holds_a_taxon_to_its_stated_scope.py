from __future__ import annotations

import contextlib
import math

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import PhyleticTree, StringValue

from pathfinder.ai.agents import frame_expression_checks
from pathfinder.ai.agents.frame_expression_checks import (
    hold_the_taxa_to_their_scope,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.named_groups import GroupScope
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.readings import AcceptedReading
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

TREE = recorded_ortho_taxonomy()
PLAS = labelled_genomes(TREE, "Plasmodium ")
SHORT = [code for code in PLAS if code not in {"pccb", "pcym"}]
ASKED = "Which groups does every Plasmodium species hold?"
WHOLE = GroupScope(taxon="Plasmodium", scope="whole")
NAMED = GroupScope(taxon="Plasmodium", scope="named")


def _per_species(genomes: list[str]) -> str:
    return " AND ".join(
        f"{'+'.join(g for g in group.genomes if g in genomes)}"
        f">={math.ceil(len(group.genomes) / 2)}T"
        for group in TREE.species_groups(genomes)
    )


def _each(genomes: list[str]) -> str:
    return " AND ".join(f"{code}>=1T" for code in genomes)


def _bound(*scopes: GroupScope) -> FrameResult:
    return FrameResult(summary="Bound.", group_scopes=list(scopes))


async def _taxonomy(site_id: str) -> PhyleticTree | None:
    return TREE


@pytest.fixture(autouse=True)
def taxonomy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(frame_expression_checks, "ortho_taxonomy", _taxonomy)


def _context(
    expression: str, message: str = ASKED, reading: AcceptedReading | None = None
) -> RunContext[AgentDeps]:
    ctx = agent_run_context(site_id="orthomcl")
    ctx.deps.agent_state.operational_spec_draft.criteria = [
        Criterion(
            id="c_groups",
            text="the groups the request asks for",
            search_name="GroupsByPhyleticPattern",
            resolved_params={
                "phyletic_expression": BoundValue(
                    value=StringValue(value=expression), source="chosen"
                )
            },
            accepted_reading=reading,
        )
    ]
    ctx.deps.agent_state.request_messages = [message]
    return ctx


async def _sent_back(ctx: RunContext[AgentDeps], result: FrameResult) -> str:
    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_taxa_to_their_scope(ctx, result)
    return str(sent_back.value)


async def test_a_whole_group_two_genomes_short_is_sent_back_naming_both() -> None:
    ctx = _context(_per_species(SHORT))

    told = await _sent_back(ctx, _bound(WHOLE))

    assert "names pccb, pcym." in told
    assert f"all of Plasmodium, {len(PLAS)} genomes" in told
    assert "as present in the unit" in told
    assert "or as absent in a unit of its own" in told
    assert ctx.deps.agent_state.refusals == 1


async def test_the_same_units_with_a_named_scope_bind() -> None:
    result = _bound(NAMED)

    assert await hold_the_taxa_to_their_scope(
        _context(_per_species(SHORT)), result
    ) is (result)


async def test_one_genome_of_one_species_needs_no_scope() -> None:
    result = _bound()
    ctx = _context("pfal>=1T", "Show every Plasmodium falciparum 3D7 group.")

    assert await hold_the_taxa_to_their_scope(ctx, result) is result


async def test_units_over_many_species_with_no_scope_are_sent_back_then_bind_a_gap() -> (
    None
):
    ctx = _context(_per_species(SHORT))
    result = _bound()

    told = await _sent_back(ctx, result)
    with contextlib.suppress(ModelRetry):
        await hold_the_taxa_to_their_scope(ctx, result)
    held = await hold_the_taxa_to_their_scope(ctx, result)

    assert "group_scopes states no scope for Plasmodium" in told
    assert "taxon 'Plasmodium'" in told
    assert held == result.with_gap(
        "group_scope_missing",
        "Scope not stated for Plasmodium, so the units of phyletic_expression in "
        "c_groups are taken as written.",
    )


@pytest.mark.parametrize("absent", ["", " AND pber=0T"])
async def test_a_whole_scope_with_an_exception_binds_without_it(absent: str) -> None:
    ctx = _context(_each([code for code in PLAS if code != "pber"]) + absent)
    result = _bound(
        GroupScope(taxon="Plasmodium", scope="whole", except_codes=["pber"])
    )

    assert await hold_the_taxa_to_their_scope(ctx, result) is result


async def test_a_scope_the_thread_holds_applies_to_a_pass_that_states_none() -> None:
    ctx = _context(_per_species(SHORT))
    ctx.deps.agent_state.held_group_scopes = {"plasmodium": WHOLE}

    assert "names pccb, pcym." in await _sent_back(ctx, _bound())


async def test_a_scope_the_pass_states_replaces_the_one_the_thread_holds() -> None:
    ctx = _context(_per_species(SHORT))
    ctx.deps.agent_state.held_group_scopes = {"plasmodium": WHOLE}
    result = _bound(NAMED)

    assert await hold_the_taxa_to_their_scope(ctx, result) is result


async def test_the_last_answer_binds_with_the_genomes_named_as_a_gap() -> None:
    ctx = _context(_per_species(SHORT))
    result = _bound(WHOLE)
    for _ in range(2):
        with pytest.raises(ModelRetry):
            await hold_the_taxa_to_their_scope(ctx, result)

    held = await hold_the_taxa_to_their_scope(ctx, result)

    assert held == result.with_gap(
        "group_genomes_left_out",
        "c_groups binds phyletic_expression over Plasmodium without pccb, pcym, "
        "and the pass states the whole of it.",
    )


async def _gap_at_the_bound(expression: str) -> FrameResult | DeferredToolRequests:
    ctx = _context(expression)
    result = _bound(WHOLE)
    for _ in range(2):
        with pytest.raises(ModelRetry):
            await hold_the_taxa_to_their_scope(ctx, result)
    return await hold_the_taxa_to_their_scope(ctx, result)


def _left_out_gap(listed: str) -> FrameResult:
    return _bound(WHOLE).with_gap(
        "group_genomes_left_out",
        f"c_groups binds phyletic_expression over Plasmodium without {listed}, "
        "and the pass states the whole of it.",
    )


async def test_a_long_list_of_left_out_genomes_names_the_first_and_counts_the_rest() -> (
    None
):
    missing = PLAS[5:]
    listed = f"{', '.join(missing[:12])} and {len(missing) - 12} more"

    assert await _gap_at_the_bound(f"{'+'.join(PLAS[:5])}>=5T") == _left_out_gap(listed)


async def test_a_list_at_the_cap_names_every_left_out_genome() -> None:
    held = PLAS[:-12]

    assert await _gap_at_the_bound(f"{'+'.join(held)}>={len(held)}T") == _left_out_gap(
        ", ".join(PLAS[-12:])
    )


async def test_an_accepted_reading_that_leaves_genomes_out_is_sent_back() -> None:
    expression = _per_species(SHORT)
    reading = AcceptedReading(
        reading="Every species", params={"phyletic_expression": expression}
    )
    ctx = _context(expression, reading=reading)

    assert "pccb, pcym" in await _sent_back(ctx, _bound(WHOLE))


async def test_a_pass_that_asks_is_not_held_to_a_scope() -> None:
    result = FrameResult(summary="Asked.", disposition="needs_user")

    assert await hold_the_taxa_to_their_scope(
        _context(_per_species(SHORT)), result
    ) is (result)


async def test_a_clade_code_stated_whole_holds_the_clade() -> None:
    ctx = _context(_per_species(SHORT))

    told = await _sent_back(ctx, _bound(GroupScope(taxon="HAEM", scope="whole")))

    assert "group_scopes states all of Haemosporida" in told
    assert "pccb, pcym" in told


VIVAX = labelled_genomes(TREE, "Plasmodium vivax ")


async def test_a_narrowed_pass_under_a_held_whole_scope_binds_its_own_scope() -> None:
    ctx = _context(f"{'+'.join(VIVAX)}>={len(VIVAX)}T")
    ctx.deps.agent_state.held_group_scopes = {"plasmodium": WHOLE}
    result = _bound(GroupScope(taxon="Plasmodium vivax", scope="whole"))

    assert await hold_the_taxa_to_their_scope(ctx, result) is result


async def test_a_narrowed_pass_with_no_scope_is_asked_for_its_own_taxon() -> None:
    ctx = _context(f"{'+'.join(VIVAX)}>={len(VIVAX)}T")
    ctx.deps.agent_state.held_group_scopes = {"plasmodium": WHOLE}

    told = await _sent_back(ctx, _bound())

    assert "State one entry with taxon 'Plasmodium vivax'" in told
    assert "all of Plasmodium," not in told


async def test_a_held_whole_scope_still_spanned_is_held_as_an_earlier_pass_stated() -> (
    None
):
    ctx = _context(_per_species(SHORT))
    ctx.deps.agent_state.held_group_scopes = {"plasmodium": WHOLE}
    result = _bound()

    told = await _sent_back(ctx, result)
    with contextlib.suppress(ModelRetry):
        await hold_the_taxa_to_their_scope(ctx, result)
    held = await hold_the_taxa_to_their_scope(ctx, result)

    assert "An earlier pass of this request stated all of Plasmodium" in told
    assert "names pccb, pcym." in told
    assert "restate taxon 'Plasmodium' as named" in told
    assert held == result.with_gap(
        "group_genomes_left_out",
        "c_groups binds phyletic_expression over Plasmodium without pccb, pcym, "
        "and an earlier pass stated the whole of it.",
    )


async def test_a_scope_restated_under_another_spelling_replaces_the_held_one() -> None:
    ctx = _context(_per_species(SHORT))
    ctx.deps.agent_state.held_group_scopes = {
        "haem": GroupScope(taxon="HAEM", scope="whole")
    }
    result = _bound(GroupScope(taxon="Haemosporida", scope="named"))

    assert await hold_the_taxa_to_their_scope(ctx, result) is result


async def test_an_exception_that_is_no_genome_of_the_taxon_is_sent_back() -> None:
    ctx = _context(_each(PLAS))
    result = _bound(
        GroupScope(taxon="Plasmodium", scope="whole", except_codes=["P. berghei"])
    )

    told = await _sent_back(ctx, result)
    with contextlib.suppress(ModelRetry):
        await hold_the_taxa_to_their_scope(ctx, result)
    held = await hold_the_taxa_to_their_scope(ctx, result)

    assert (
        "except_codes of taxon 'Plasmodium' names P. berghei, which is no genome "
        f"of Plasmodium. Its genome codes are {', '.join(PLAS[:12])} and "
        f"{len(PLAS) - 12} more."
    ) == told
    assert held == result.with_gap(
        "group_scope_exception_unknown",
        "except_codes of Plasmodium names P. berghei, which is no genome of it, so "
        "nothing is left out for it.",
    )
