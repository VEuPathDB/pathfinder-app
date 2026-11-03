from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.services.strategies.expression_readings import expression_readings
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PARAM = "phyletic_expression"
_INFO = ParameterInfo.model_validate(
    {
        "name": _PARAM,
        "display_name": "Expression",
        "type": "string",
        "required": True,
        "is_visible": True,
        "help": "",
        "value_format": "",
    }
)


def test_the_row_states_the_share_of_the_genus() -> None:
    tree = recorded_ortho_taxonomy()
    plasmodium = "+".join(labelled_genomes(tree, "Plasmodium "))
    toxoplasma = "+".join(labelled_genomes(tree, "Toxoplasma "))
    bound = BoundValue(
        value=StringValue(value=f"{plasmodium}>=55T AND {toxoplasma}=0T"),
        source="chosen",
    )
    criterion = Criterion(
        id="c_groups",
        text="groups",
        search_name="GroupsByPhyleticPattern",
        resolved_params={_PARAM: bound},
        param_display_names={_PARAM: "Expression"},
        measurements=expression_readings({_PARAM: bound}, {_PARAM: _INFO}, tree),
    )
    spec = OperationalSpec(goal="groups", criteria=[criterion])
    deps = lead_deps(
        pipeline_state("orthomcl", domain=StrategyDomainState(operational_spec=spec))
    )

    [step] = turn_facts(deps).steps
    [row] = [p for p in step.parameters if p.name == _PARAM]

    assert row.value == (
        "at least 55 of the 61 genomes of Plasmodium and none of the 15 genomes of "
        "Toxoplasma gondii"
    )
