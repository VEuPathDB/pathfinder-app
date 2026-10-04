"""A dependent pick first read from a strategy is labelled on the vocabulary
its step's own parent values answer."""

from __future__ import annotations

from collections.abc import Collection

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import WDKError
from veupathdb_mcp.catalog import ParameterInfo, ParamFetcher, format_param_info_typed

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.answered_strategy import the_changes_written_outside
from pathfinder.ai.lead.pre_turn import stated_spec_of
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import sheet_params
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.sheets import visible_sheet
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

# plasmodb GenesByInterproDomain: the published sheet under its default
# organism, and the read under Plasmodium falciparum 3D7 and Pfam.
_DOMAINS = "GenesByInterproDomain"
_TEXT = "GenesByText"
_PUBLISHED = [
    info
    for info in format_param_info_typed(
        suite_search("search_genes_by_interpro_domain").parameters or []
    )
    if info.is_visible
]
_UNDER_PF3D7 = format_param_info_typed(
    suite_search("search_genes_by_interpro_domain_under_pf3d7_pfam").parameters or []
)
_PF3D7_CONTEXT = {
    "organism": '["Plasmodium falciparum 3D7"]',
    "domain_database": "Pfam",
    "domain_typeahead": '["PF00013"]',
}
_PUBLISHED_ORGANISM = ["Haemoproteidae", "Haemoproteus tartakovskyi strain SISKIN1"]
_KINASE = {"text_expression": StringValue(value="kinase")}


def _domain_step(
    step_id: str = "dom",
    *,
    organism: Collection[str] = ("Plasmodium falciparum 3D7",),
    domain: str = "PF00013",
) -> StrategyStepNode:
    parameters: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=list(organism)),
        "domain_database": SinglePickValue(value="Pfam"),
        "domain_typeahead": MultiPickValue(values=[domain]),
    }
    return StrategyStepNode(id=step_id, search_name=_DOMAINS, parameters=parameters)


def _text_step(step_id: str = "dom", text: str = "kinase") -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=_TEXT,
        parameters={"text_expression": StringValue(value=text)},
    )


def _joined(primary: StrategyStepNode, secondary: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id="join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=primary,
        secondary_input=secondary,
    )


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def _graph(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="KH domains", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


def _spec(criterion: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="genes with a KH domain",
        record_type="transcript",
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )


def _label(spec: OperationalSpec | None, criterion_id: str = "dom") -> str:
    assert spec is not None
    criterion = next(c for c in spec.criteria if c.id == criterion_id)
    return criterion.resolved_params["domain_typeahead"].label


class _Reads:
    """The contexts the domain search was read under."""

    def __init__(self) -> None:
        self.contexts: list[tuple[str, str, dict[str, str]]] = []

    def fetch_at(
        self, _site_id: str, record_type: str, search_name: str
    ) -> ParamFetcher:
        async def fetch(context: dict[str, str]) -> list[ParameterInfo]:
            self.contexts.append((record_type, search_name, context))
            return _UNDER_PF3D7

        return fetch


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> _Reads:
    served = _Reads()
    published = {_DOMAINS: _PUBLISHED, _TEXT: visible_sheet(["text_expression"])}

    async def _sheets(
        *, site_id: str, record_type: str | None, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, record_type
        return {name: published[name] for name in search_names}

    async def _marks(
        _site_id: str, _record_type: str | None, _searches: Collection[str]
    ) -> dict[str, str]:
        return {}

    for module in (answered_strategy, pre_turn):
        monkeypatch.setattr(module, "sheet_params_for_searches", _sheets)
        monkeypatch.setattr(module, "organism_parameters", _marks)
    monkeypatch.setattr(sheet_params, "wdk_fetch_at", served.fetch_at)
    return served


async def test_a_step_the_site_moved_onto_the_domain_search_labels_its_pick(
    reads: _Reads,
) -> None:
    spec = _spec(
        Criterion(
            id="dom",
            text="KH domain",
            search_name=_TEXT,
            resolved_params=bound(_KINASE),
        )
    )
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec, answered_spec=spec, answered_graph=_ast(_text_step())
        )
    )

    await the_changes_written_outside(
        state, site_id="plasmodb", graph=_graph(_domain_step())
    )

    assert (
        _label(state.domain.answered_spec),
        _label(state.domain.operational_spec),
    ) == ("KH domain", "KH domain")
    assert reads.contexts == [("transcript", _DOMAINS, _PF3D7_CONTEXT)]


async def test_a_pick_the_site_edited_is_labelled_under_its_organism(
    reads: _Reads,
) -> None:
    answered = _domain_step(domain="PF00051")
    spec = _spec(
        Criterion(
            id="dom",
            text="KH domain",
            search_name=_DOMAINS,
            resolved_params=bound(answered.parameters),
        )
    )
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec, answered_spec=spec, answered_graph=_ast(answered)
        )
    )

    await the_changes_written_outside(
        state, site_id="plasmodb", graph=_graph(_domain_step())
    )

    assert _label(state.domain.answered_spec) == "KH domain"
    assert reads.contexts == [("transcript", _DOMAINS, _PF3D7_CONTEXT)]


async def test_a_step_the_site_added_is_labelled_under_its_organism(
    reads: _Reads,
) -> None:
    spec = _spec(
        Criterion(
            id="txt", text="kinases", search_name=_TEXT, resolved_params=bound(_KINASE)
        )
    )
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec,
            answered_spec=spec,
            answered_graph=_ast(_text_step("txt")),
        )
    )

    await the_changes_written_outside(
        state,
        site_id="plasmodb",
        graph=_graph(_joined(_text_step("txt"), _domain_step())),
    )

    assert _label(state.domain.answered_spec) == "KH domain"
    assert reads.contexts == [("transcript", _DOMAINS, _PF3D7_CONTEXT)]


async def test_a_hydrated_step_is_labelled_under_its_organism(reads: _Reads) -> None:
    stated = await stated_spec_of(
        _ast(_domain_step()), site_id="plasmodb", goal="genes with a KH domain"
    )

    assert _label(stated) == "KH domain"
    assert reads.contexts == [("transcript", _DOMAINS, _PF3D7_CONTEXT)]


async def test_a_step_with_no_dependent_parameter_reads_no_vocabulary(
    reads: _Reads,
) -> None:
    spec = _spec(
        Criterion(
            id="dom", text="kinases", search_name=_TEXT, resolved_params=bound(_KINASE)
        )
    )
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec, answered_spec=spec, answered_graph=_ast(_text_step())
        )
    )

    await the_changes_written_outside(
        state, site_id="plasmodb", graph=_graph(_text_step(text="phosphatase"))
    )

    assert reads.contexts == []


async def test_a_step_the_site_cannot_read_is_labelled_on_the_published_sheet(
    monkeypatch: pytest.MonkeyPatch, reads: _Reads
) -> None:
    def _unreadable(_site_id: str, _record_type: str, search_name: str) -> ParamFetcher:
        async def fetch(_context: dict[str, str]) -> list[ParameterInfo]:
            msg = f"{search_name} is unreachable"
            raise WDKError(msg, 503)

        return fetch

    monkeypatch.setattr(sheet_params, "wdk_fetch_at", _unreadable)

    stated = await stated_spec_of(
        _ast(_domain_step()), site_id="plasmodb", goal="genes with a KH domain"
    )

    assert _label(stated) == ""
    assert reads.contexts == []


async def test_a_step_under_the_published_parents_reads_no_vocabulary(
    reads: _Reads,
) -> None:
    stated = await stated_spec_of(
        _ast(_domain_step(organism=_PUBLISHED_ORGANISM)),
        site_id="plasmodb",
        goal="genes with a KH domain",
    )

    assert _label(stated) == ""
    assert reads.contexts == []
