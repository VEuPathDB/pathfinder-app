from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.wdk import WDKSearch

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.genome_group import (
    GenomeGroup,
    UnnamedGenomeGroupError,
)
from pathfinder.domain.strategy.genome_group_steps import spec_read_on_genomes
from pathfinder.domain.strategy.measurement_clauses import genome_reading_clauses
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import genome_group_names
from pathfinder.services.strategies.genome_group_names import (
    spec_with_its_genomes_named,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.recorded_searches import suite_search

_SEARCH = "GenesByOrthologPattern"
_PATTERN = suite_search("search_genes_by_ortholog_pattern")
_PAIR = ("pber", "pfal")
_NAME = "2 genomes in Plasmodium berghei ANKA and Plasmodium falciparum 3D7"


def _criterion(group: GenomeGroup | None, criterion_id: str = "c_profile") -> Criterion:
    return Criterion(
        id=criterion_id,
        text="an ortholog in the group.",
        search_name=_SEARCH,
        record_class="transcript",
        genome_group=group,
        resolved_params=bound(
            {"profile_pattern": StringValue(value="%hsap:N%pber:Y%pfal:Y%")}
        ),
    )


def _stored_before_groups_had_names(reading: str) -> OperationalSpec:
    right = _criterion(None, "c_profile_absent").model_copy(
        update={"text": "an ortholog in the group. (none of 2 genomes)"}
    )
    dumped = OperationalSpec(
        goal="orthologs",
        criteria=[
            _criterion(GenomeGroup(reading="all", genomes=_PAIR, name=_NAME)),
            right.model_copy(update={"absence_of": "c_profile"}),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_profile")
        ),
    ).model_dump(by_alias=True, mode="json")
    for criterion in dumped["criteria"]:
        del criterion["requiredGenomesName"]
    dumped["criteria"][0]["genomeGroup"] = {"reading": reading, "genomes": list(_PAIR)}
    return OperationalSpec.model_validate(dumped)


@pytest.fixture
def _recorded_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _listed(_site_id: str, names: object) -> dict[str, str]:
        return {_SEARCH: "transcript"}

    async def _definition(_site_id: str, _record_type: str, _name: str) -> WDKSearch:
        return _PATTERN

    monkeypatch.setattr(genome_group_names, "search_record_types", _listed)
    monkeypatch.setattr(genome_group_names, "read_search_definition", _definition)


def test_a_stored_group_with_no_name_loads_unnamed() -> None:
    [left, _] = _stored_before_groups_had_names("all").criteria

    assert left.genome_group == GenomeGroup(reading="all", genomes=_PAIR)
    assert left.genome_group is not None
    assert not left.genome_group.named


@pytest.mark.asyncio
@pytest.mark.usefixtures("_recorded_pattern")
async def test_the_next_turn_names_a_stored_group_from_the_sites_tree() -> None:
    named = await spec_with_its_genomes_named(
        _stored_before_groups_had_names("at_least_one"), site_id="plasmodb"
    )

    assert named is not None
    left, right = named.criteria
    assert left.genome_group == GenomeGroup(
        reading="at_least_one", genomes=_PAIR, name=_NAME
    )
    assert (left.text, right.text) == (
        f"an ortholog in the group; an ortholog in at least one of the {_NAME}",
        f"an ortholog in the group; no ortholog in any of the {_NAME}",
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_recorded_pattern")
async def test_a_profile_awaiting_its_card_is_named_and_its_answer_names_the_group() -> (
    None
):
    spec = OperationalSpec(
        goal="orthologs",
        criteria=[_criterion(None)],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_profile")
        ),
    )

    named = await spec_with_its_genomes_named(spec, site_id="plasmodb")
    assert named is not None
    read = spec_read_on_genomes(
        named, "c_profile", GenomeGroup(reading="all", genomes=_PAIR)
    )

    [settled] = read.criteria
    assert settled.genome_group == GenomeGroup(reading="all", genomes=_PAIR, name=_NAME)
    assert settled.text == f"an ortholog in the group; an ortholog in all {_NAME}"


def test_an_unnamed_group_never_reaches_a_card_or_a_text() -> None:
    unnamed = GenomeGroup(reading="at_least_one", genomes=_PAIR)

    with pytest.raises(UnnamedGenomeGroupError):
        _ = unnamed.built_words
    with pytest.raises(UnnamedGenomeGroupError):
        unnamed.stated_in("an ortholog in the group")
    with pytest.raises(UnnamedGenomeGroupError):
        unnamed.absent_in("an ortholog in the group")
    with pytest.raises(UnnamedGenomeGroupError):
        genome_reading_clauses(_criterion(unnamed), noun="gene")
    with pytest.raises(UnnamedGenomeGroupError):
        spec_read_on_genomes(
            OperationalSpec(goal="orthologs", criteria=[_criterion(None)]),
            "c_profile",
            unnamed,
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_recorded_pattern")
async def test_the_turn_entry_names_the_stored_group_before_the_turn_runs() -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=StrategyDomainState(
            operational_spec=_stored_before_groups_had_names("all")
        ),
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )

    refreshed = await refresh_live_strategy_state(state, context)

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert spec.criteria[0].genome_group == GenomeGroup(
        reading="all", genomes=_PAIR, name=_NAME
    )
