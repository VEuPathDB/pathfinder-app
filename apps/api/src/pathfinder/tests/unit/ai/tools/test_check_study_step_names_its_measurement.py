"""``check_study_step`` states the measurement the compute ran on, by the study's
name for it, so a request for one count type is read against the one that ran."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import flatten_tree
from veupathdb.eda import (
    EdaError,
    EdaForbiddenError,
    EdaPermissionEntry,
    EdaServerError,
    EdaStudyDetail,
)

from pathfinder.ai.tools.standalone import study_step
from pathfinder.ai.tools.standalone.study_step import (
    StudyStepCheck,
    check_study_step,
)
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.eda.catalog import UnknownEdaDatasetError
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.eda_doubles import permission_entry
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of
from pathfinder.tests.unit.domain.strategy._analysis import (
    ANTISENSE_COUNT,
    COMPUTE_SEARCH,
    E2_STEP,
    SENSE_COUNT,
    e2_step,
)

_COUNTS_ENTITY = "ENT_fd574cd6"
_KEPT = "genes that differ between wildtype and delta-DHC mutant"


def _count(variable_id: str, name: str) -> dict[str, str]:
    return {
        "id": variable_id,
        "displayName": name,
        "type": "integer",
        "dataShape": "continuous",
    }


def _counts_study() -> EdaStudyDetail:
    """The E2 study: a sample entity above the count entity.

    The sample entity declares a variable with the sense column's id, which
    EDA allows, since a variable id is scoped to its entity.
    """
    return EdaStudyDetail.model_validate(
        {
            "id": "STUDY_e973eadd57",
            "rootEntity": {
                "id": "ENT_8151325d",
                "displayName": "Sample",
                "variables": [_count(SENSE_COUNT, "Sample read total")],
                "children": [
                    {
                        "id": _COUNTS_ENTITY,
                        "displayName": "Gene counts",
                        "variables": [
                            _count(ANTISENSE_COUNT, "Antisense Count"),
                            _count(SENSE_COUNT, "Sense Count"),
                        ],
                    }
                ],
            },
        }
    )


@pytest.fixture(autouse=True)
def _serve_the_study(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _detail(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        return permission_entry(), _counts_study()

    monkeypatch.setattr(study_step, "get_study_detail_for_dataset", _detail)


async def _check(
    value_variable: str, requested_fold_change: float = 2
) -> tuple[StudyStepCheck, str]:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "Heat shock DHC", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(e2_step(value_variable)))
    graph.recompute_roots()
    graph.note_analysis_kinds(
        {E2_STEP: StampedKind(search_name=COMPUTE_SEARCH, kind=AnalysisKind.COMPUTE)}
    )
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={E2_STEP: 201})
    answer = await check_study_step(
        agent_run_context(strategy_session=session),
        E2_STEP,
        requested_fold_change=requested_fold_change,
        requested_significance=0.05,
    )
    return returned(answer, StudyStepCheck), str(summary_of(answer).data["summary"])


async def test_the_e2_step_states_the_sense_count_column() -> None:
    check, summary = await _check(SENSE_COUNT)

    assert check.value_variable == "Sense Count"
    assert summary == (
        f"201 records at 2-fold and p 0.05, DESeq on Sense Count: {_KEPT}"
    )


async def test_a_compute_on_the_antisense_column_states_that_column() -> None:
    """A request for sense counts reads against what ran, never its own words."""
    check, summary = await _check(ANTISENSE_COUNT)

    assert check.value_variable == "Antisense Count"
    assert summary == (
        f"201 records at 2-fold and p 0.05, DESeq on Antisense Count: {_KEPT}"
    )


@pytest.mark.parametrize(
    "refusal",
    [
        UnknownEdaDatasetError("DS_e973eadd57", []),
        EdaForbiddenError("Forbidden", 403),
        EdaServerError("Internal Server Error", 500),
    ],
    ids=["unknown", "forbidden", "server"],
)
async def test_a_study_the_check_cannot_read_states_the_variable_id(
    monkeypatch: pytest.MonkeyPatch, refusal: UnknownEdaDatasetError | EdaError
) -> None:
    """The step's own document states what ran, so the check still reports it."""

    async def _refuse(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        raise refusal

    monkeypatch.setattr(study_step, "get_study_detail_for_dataset", _refuse)

    check, _summary = await _check(SENSE_COUNT)

    assert (check.method, check.value_variable) == ("DESeq", SENSE_COUNT)


async def test_a_value_the_step_was_not_built_at_leads_the_summary() -> None:
    check, summary = await _check(SENSE_COUNT, requested_fold_change=1.5)

    assert [(c.label, c.honored) for c in check.checks] == [
        ("fold change", False),
        ("significance", True),
    ]
    assert summary.startswith(
        "Not met: fold change asked 1.5, built 2. 201 records at 2-fold and p 0.05"
    )
