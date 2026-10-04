"""The values a replay binds afresh on each live step, and a criterion read
again on the sheet its step's own parents answer."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.spec_hydration import (
    read_under_their_parents,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_replay import steps_the_replay_reads
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.tests._support.recorded_searches import suite_search

from ._builders import combine

_PUBLISHED = format_param_info_typed(
    suite_search("search_genes_by_interpro_domain").parameters or []
)
_UNDER_PF3D7 = format_param_info_typed(
    suite_search("search_genes_by_interpro_domain_under_pf3d7_pfam").parameters or []
)
_EXPRESSION = "GenesByRNASeqEvidence"
_DOMAINS = "GenesByInterproDomain"


def _step(step_id: str, search_name: str, **values: ParamValue) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name, parameters=values)


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def _expression(percentile: int) -> StrategyStepNode:
    return _step(
        "expr",
        _EXPRESSION,
        min_expression_percentile=NumberValue(value=percentile),
        timepoint=NumberValue(value=40),
    )


def _read(answered: StrategyAst, live: StrategyAst) -> dict[str, frozenset[str]]:
    stated = {"expr", "text"}
    reads = steps_the_replay_reads(outside_changes(answered, live), live, stated)
    return {read.node.id: read.names for read in reads}


def test_a_value_moved_outside_is_the_only_value_its_step_binds() -> None:
    text = _step("text", "GenesByText")

    reads = _read(
        _ast(combine("c0", text, _expression(80))),
        _ast(combine("c0", text, _expression(48))),
    )

    assert reads == {"expr": frozenset({"min_expression_percentile"})}


def test_a_step_moved_onto_another_search_binds_every_value() -> None:
    domains = _step(
        "expr",
        _DOMAINS,
        organism=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
        domain_database=SinglePickValue(value="Pfam"),
    )

    reads = _read(_ast(_expression(80)), _ast(domains))

    assert reads == {"expr": frozenset({"organism", "domain_database"})}


def test_a_step_no_spec_states_binds_every_value() -> None:
    added = _step("added", _DOMAINS, domain_database=SinglePickValue(value="Pfam"))

    reads = _read(_ast(_expression(80)), _ast(combine("c0", _expression(80), added)))

    assert reads == {"added": frozenset({"domain_database"})}


def test_a_criterion_is_read_again_on_the_sheet_its_parents_answer() -> None:
    step = _step(
        "dom",
        _DOMAINS,
        organism=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
        domain_typeahead=MultiPickValue(values=["PF00013"]),
    )
    spec = spec_from_ast(_ast(step), goal="KH domains")

    read = read_under_their_parents(spec, {"dom": _UNDER_PF3D7})

    assert read.criteria[0].resolved_params["domain_typeahead"].label == "KH domain"


def test_a_criterion_no_parents_read_names_is_left_as_it_is() -> None:
    held = bind_values(
        {"domain_typeahead": MultiPickValue(values=["PF00013"])}, "held", _PUBLISHED
    )
    spec = OperationalSpec(
        goal="KH domains",
        criteria=[
            Criterion(id="dom", text="KH", search_name=_DOMAINS, resolved_params=held)
        ],
    )

    assert read_under_their_parents(spec, {"other": _UNDER_PF3D7}) == spec
