"""A column read that finds no column a criterion binds names the step's
countable columns, the same columns step_columns lists."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._result_models import (
    StepColumns,
    no_column,
    with_countable,
)
from pathfinder.ai.tools.standalone.results import read_step_columns
from pathfinder.domain.column_reach import ReachedColumn
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests._support.orthomcl_step_columns import serve_sequence_columns
from pathfinder.tests._support.tool_returns import returned

from ._strategy_edit_stubs import session_with
from .conftest import agent_run_context

PROTEIN_STEP = 227288390
TAXON_CODE = ReachedColumn(name="abbreviation", display_name="Taxon Code")


async def test_the_recorded_protein_step_names_the_taxon_code_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    listed = serve_sequence_columns(monkeypatch, PROTEIN_STEP, "FromGroups")
    session = session_with(
        StrategyStepNode(id="c_proteins", search_name="FromGroups"),
        {"c_proteins": PROTEIN_STEP},
    )
    session.site_id = "orthomcl"
    state = AgentToolState()
    state.frame_set_criterion(
        Criterion(
            id="c_proteins",
            text="the proteins in the singleton ortholog groups",
            search_name="FromGroups",
        )
    )

    result = await read_step_columns(
        agent_run_context(
            site_id="orthomcl", strategy_session=session, agent_state=state
        ),
        PROTEIN_STEP,
    )

    answer = returned(result, StepColumns)
    assert (answer.fits, answer.countable, listed) == (
        [],
        [TAXON_CODE],
        [PROTEIN_STEP],
    )
    assert answer.note == (
        f"Step {PROTEIN_STEP} is not a gene search step a criterion binds. "
        "Sample the root with get_sample_records for this criterion. "
        "Its records count by abbreviation (Taxon Code)."
    )


def test_the_recorded_group_step_says_no_column_counts_its_records() -> None:
    group_step = 227288450
    why = f"Step {group_step} is not a gene search step a criterion binds."

    columns, summary = with_countable(*no_column(group_step, why), [])

    assert (columns.countable, summary) == (
        [],
        f"No column of step {group_step}. None of its columns counts its records.",
    )
    assert columns.note.endswith("None of its columns counts its records.")
