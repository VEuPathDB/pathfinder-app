from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    PhyleticBinding,
    PhyleticTree,
    StringValue,
    derive_binding,
)
from veupathdb.wdk import WDKParameter, phyletic_tree_of
from veupathdb_mcp.catalog import FilterReads, ParamFetcher

from strategist.ai.agents.state import AgentToolState
from strategist.ai.agents.strategy_instructions import pinned_frame_workspace
from strategist.ai.lead.edit_messages import EditMessage, edit_work_order
from strategist.ai.tools.standalone import _frame_proposals, frame_spec
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    held_binding,
)
from strategist.domain.strategy.genome_group import GenomeGroup
from strategist.domain.strategy.genome_group_steps import spec_read_on_genomes
from strategist.domain.strategy.genome_set_names import genome_set_name
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.spec_diff import SpecDiff
from strategist.tests._support.bound_values import bound
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.recorded_counts import no_measurements
from strategist.tests._support.recorded_searches import (
    no_count,
    serve_recorded,
    suite_search,
)
from strategist.tests.unit.ai.tools.conftest import serve_no_other_sites
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

_ORTHOLOGS = suite_search("search_genes_by_ortholog_pattern")
_TREE = phyletic_tree_of(list(_ORTHOLOGS.parameters or [])) or PhyleticTree()
_PAIR = ("pber", "pfal")
_ID = "c_profile"
_PF = "Plasmodium falciparum 3D7"


def _census() -> dict[str, str]:
    match derive_binding(_TREE, list(_PAIR), []):
        case PhyleticBinding() as derived:
            return derived.model_dump()
        case refused:
            raise AssertionError(refused)


def _read() -> OperationalSpec:
    values: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=[_PF]),
        **{name: StringValue(value=wire) for name, wire in _census().items()},
    }
    stated = Criterion(
        id=_ID,
        text="an ortholog in the pair",
        search_name="GenesByOrthologPattern",
        record_class="transcript",
        role="seed",
        resolved_params=bound(values),
    )
    group = GenomeGroup(
        reading="at_least_one", genomes=_PAIR, name=genome_set_name(_TREE, _PAIR)
    )
    spec = OperationalSpec(
        goal="orthologs",
        criteria=[stated],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id=_ID)),
    )
    return spec_read_on_genomes(spec, _ID, group)


def _ctx(spec: OperationalSpec) -> Any:
    ctx = MagicMock()
    ctx.deps.agent_state.operational_spec_draft = spec
    return ctx


def _shown(name: str) -> str:
    return f'    {name}="{_census()[name]}"'


def _reading() -> str:
    name = genome_set_name(_TREE, _PAIR)
    return f"    reading: an ortholog in at least one of the {name}. The values below"


def test_the_workspace_shows_the_left_as_its_census() -> None:
    spec = _read()
    assert spec.criteria[0].resolved_params["profile_pattern"].value == StringValue(
        value="%"
    )

    rendered = pinned_frame_workspace(_ctx(spec)) or ""

    assert _reading() in rendered
    assert rendered.index(_reading()) < rendered.index(_shown("profile_pattern"))
    assert _shown("included_species") in rendered
    assert '    profile_pattern="%"\n' not in rendered


def test_a_work_order_shows_the_left_as_its_census() -> None:
    spec = _read()

    order = edit_work_order(
        "the researcher moves the organism",
        EditMessage(prompt="use 3D7"),
        spec,
        pending=SpecDiff(),
        answered=spec,
    )

    assert _reading() in order
    assert _shown("profile_pattern") in order
    assert '    profile_pattern="%"\n' not in order


def test_a_rebind_of_the_left_holds_its_census() -> None:
    state = AgentToolState()
    state.operational_spec_draft = _read()
    call = CriterionCall(
        criterion_id=_ID,
        search_name="GenesByOrthologPattern",
        text="an ortholog in the pair",
        params={"organism": [_PF]},
    )

    held = held_binding(state, call, sheet_of(list(_ORTHOLOGS.parameters or [])))

    lists = ("included_species", "excluded_species")
    assert {name: held[name].value for name in lists} == {
        name: StringValue(value=_census()[name]) for name in lists
    }


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    list_every_search_under(monkeypatch, "transcript")
    serve_recorded(monkeypatch, [_ORTHOLOGS])

    def _fetch_at(_site: str, _record_type: str, _search: str) -> ParamFetcher:
        async def fetch_at(_context: dict[str, str]) -> list[WDKParameter]:
            return list(_ORTHOLOGS.parameters or [])

        return fetch_at

    def _reads(_site: str, _record_type: str, _search: str) -> FilterReads:
        return NoFilterReads()

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)
    monkeypatch.setattr(_frame_proposals, "WDKFilterReads", _reads)
    no_validation(monkeypatch)
    no_count(monkeypatch)
    no_measurements(monkeypatch)
    serve_site_listing(monkeypatch, [])
    serve_no_other_sites(monkeypatch)


async def test_the_left_rebound_on_its_organism_keeps_its_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()
    read = _read()
    state.operational_spec_draft = read
    left = read.criteria[0]

    await bind(
        state,
        "GenesByOrthologPattern",
        {"organism": [_PF]},
        criterion_id=_ID,
        text=left.text,
    )

    rebound = next(c for c in state.operational_spec_draft.criteria if c.id == _ID)
    assert rebound.genome_group == left.genome_group
    assert rebound.resolved_params["profile_pattern"].value == StringValue(
        value=_census()["profile_pattern"]
    )
