"""An export the graph editor or the site added is stated with the study's names
and its compute's counts, as an export the thread wrote is."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
)
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.domain.strategy.analysis_binding import (
    AnalysisBinding,
    AnalysisKind,
    CutTallies,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.services.eda.catalog import UnknownEdaDatasetError
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.export import exported_analysis, read_the_export
from pathfinder.services.eda.steps import eda_step_node
from pathfinder.tests._support.eda_step_doubles import (
    DE_DATASET,
    SAMPLE_ENTITY,
    de_analysis,
    de_study,
    wire_export_reads,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    leaf,
    session_holding,
)

_ADDED = "step_5e1f0a2b"
_CUT = VolcanoThresholds(
    effect_size_threshold=1.0, significance_threshold=0.05, effect_direction="upOnly"
)
# The recorded volcano statistics of the RNA-Seq study, counted at that cut.
_TALLIES = CutTallies(
    tested=200,
    retained=33,
    retained_up=33,
    retained_down=34,
    at_any_effect=55,
    at_any_significance=49,
)


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("researcher.token")
    yield
    veupathdb_auth_token_ctx.reset(handle)


def _wild_type() -> EdaAnalysisDetail:
    """The febrile against normal comparison, on the wild type samples."""
    return de_analysis(
        filters=[
            EdaStringSetFilter(
                entity_id=SAMPLE_ENTITY,
                variable_id="VAR_84f17484",
                string_set=["wildtype"],
            )
        ],
        with_computation=True,
    )


async def _written(
    cut: VolcanoThresholds | None,
) -> tuple[StrategyStepNode, AnalysisBinding]:
    """The step an export of the thread writes, and the binding it states."""
    analysis = _wild_type()
    reading = await read_the_export(
        "plasmodb", dataset_id=DE_DATASET, analysis=analysis, thresholds=cut
    )
    plan = eda_step_node(
        analysis, dataset_id=DE_DATASET, thresholds=cut, reading=reading
    )
    added = plan.node.model_copy(
        update={"id": _ADDED, "search_name": COMPUTE_QUERY if cut else SUBSET_QUERY}
    )
    return added, plan.binding


def _unspecified(
    monkeypatch: pytest.MonkeyPatch, step: StrategyStepNode
) -> DisagreementThread:
    """A thread whose strategy holds the step and no spec describes it."""
    thread = DisagreementThread(
        monkeypatch, spec=OperationalSpec(), session=session_holding(step)
    )
    thread.deps.state.domain.operational_spec = None
    return thread


def _reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve the recorded study and statistics, and record each study read."""
    reads: list[str] = []

    async def _study(
        site_id: str, dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        reads.append(dataset_id)
        return await de_study(site_id, dataset_id)

    wire_export_reads(monkeypatch, study=_study)
    return reads


async def test_a_compute_export_added_outside_states_the_binding_the_thread_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reads(monkeypatch)
    step, written = await _written(_CUT)
    thread = _unspecified(monkeypatch, step)

    await thread.next_turn()

    [criterion] = thread.spec.criteria
    assert criterion.analysis == written
    assert (
        written.subset_as_shown(),
        written.value_variable_name,
        written.tallies,
    ) == (["genotype is one of wildtype"], "Sense Count", _TALLIES)


async def test_a_subset_export_added_outside_names_its_filters_as_the_study_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reads(monkeypatch)
    step, written = await _written(None)
    thread = _unspecified(monkeypatch, step)

    await thread.next_turn()

    [criterion] = thread.spec.criteria
    assert criterion.analysis == written
    assert (written.subset_as_shown(), written.tallies) == (
        ["genotype is one of wildtype"],
        None,
    )


async def test_a_binding_stated_from_its_document_alone_is_named_on_every_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reads(monkeypatch)
    step, written = await _written(_CUT)
    unread = exported_analysis(AnalysisKind.COMPUTE, step.parameters)
    assert unread is not None
    spec = OperationalSpec(
        goal="febrile over normal",
        criteria=[Criterion(id=_ADDED, text=unread.words, analysis=unread)],
        structure=SpecStructure(root=leaf(_ADDED)),
    )
    thread = DisagreementThread(monkeypatch, spec=spec, session=session_holding(step))

    await thread.next_turn()

    assert [
        [c.analysis for c in held.criteria]
        for held in (thread.spec, thread.answered, thread.before_turn)
    ] == [[written], [written], [written]]


async def test_a_named_binding_reads_the_study_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = _reads(monkeypatch)
    step, _written_binding = await _written(_CUT)
    thread = _unspecified(monkeypatch, step)
    reads.clear()

    await thread.next_turn()
    await thread.next_turn()

    assert reads == [DE_DATASET]


async def test_a_study_that_cannot_be_read_leaves_the_binding_its_document_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reads(monkeypatch)
    step, _written_binding = await _written(_CUT)

    async def _unknown(
        _site: str, dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        raise UnknownEdaDatasetError(dataset_id, [])

    wire_export_reads(monkeypatch, study=_unknown)
    thread = _unspecified(monkeypatch, step)

    await thread.next_turn()

    [criterion] = thread.spec.criteria
    assert criterion.analysis is not None
    assert (
        criterion.analysis.subset_as_shown(),
        criterion.analysis.value_variable_name,
        criterion.analysis.tallies,
    ) == (["VAR_84f17484 is one of wildtype"], "", None)
