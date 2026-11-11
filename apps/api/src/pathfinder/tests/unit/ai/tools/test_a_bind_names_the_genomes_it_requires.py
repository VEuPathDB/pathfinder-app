from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PhyleticTree, StringValue
from veupathdb.wdk import phyletic_tree_of
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_measure import record_measurements
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_PATTERN = suite_search("search_genes_by_ortholog_pattern")
_TREE = phyletic_tree_of(list(_PATTERN.parameters or [])) or PhyleticTree()


@pytest.mark.asyncio
async def test_a_profile_bind_records_the_name_of_its_required_genomes() -> None:
    tokens = "%".join(f"{code}:Y" for code in sorted(_TREE.genomes_under(["OOMY"])))
    criterion = Criterion(
        id="c_profile",
        text="an ortholog in oomycetes",
        search_name="GenesByOrthologPattern",
        resolved_params=bound(
            {
                "profile_pattern": StringValue(value=f"%{tokens}%"),
                "included_species": StringValue(value="OOMY"),
            }
        ),
    )
    ctx = agent_run_context(site_id="plasmodb")
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        goal="orthologs", criteria=[criterion]
    )

    await record_measurements(
        ctx,
        criterion,
        record_type="transcript",
        params=criterion.param_values,
        count=None,
        definition=_PATTERN,
        infos=format_param_info_typed(list(_PATTERN.parameters or [])),
    )

    [stored] = ctx.deps.agent_state.operational_spec_draft.criteria
    assert stored.required_genomes_name == "28 Oomycota genomes"
