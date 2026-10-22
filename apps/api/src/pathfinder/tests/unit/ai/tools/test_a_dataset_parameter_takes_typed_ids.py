from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import InputDatasetValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.orthomcl_site import (
    BY_ID_LIST,
    PROTEINS_OF_THE_TYPED_ID,
    TYPED_GENE_ID,
    OrthoSite,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._orthomcl_site import (
    group_strategy_ctx,
    serve_orthomcl,
)

_MESSAGE = f"Look the protein up by its ID {TYPED_GENE_ID} and give me its group."
_WHY = SearchChoice(
    basis="only_match",
    term="ByIdList",
    reason="ByIdList finds proteins by a VEuPathDB gene id",
)


def _state(message: str = _MESSAGE) -> AgentToolState:
    state = AgentToolState(request_messages=[message])
    state.record_catalog_read(listing(["ByIdList"], record_type="sequence"))
    return state


async def _bind(state: AgentToolState, params: ParamProposals) -> SetCriterionResult:
    return returned(
        await set_criterion(
            group_strategy_ctx(state),
            criterion_id="c_protein",
            text=f"the protein {TYPED_GENE_ID}",
            search_name="ByIdList",
            role="seed",
            params=params,
            why=_WHY,
        ),
        SetCriterionResult,
    )


def _bound(state: AgentToolState) -> tuple[object, str, str, str]:
    [criterion] = state.operational_spec_draft.criteria
    held = criterion.resolved_params["source_ids"]
    return held.value, held.source, held.basis, held.label


def test_the_recorded_search_takes_a_dataset() -> None:
    [parameter] = BY_ID_LIST.parameters or []

    assert (parameter.name, parameter.type) == ("source_ids", "input-dataset")


async def test_a_typed_gene_id_binds_as_an_id_list_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)
    state = _state()

    result = await _bind(state, {"source_ids": TYPED_GENE_ID})

    assert site.datasets == [[TYPED_GENE_ID]]
    assert all(TYPED_GENE_ID not in context.values() for context in site.contexts)
    assert site.counted == [
        ("ByIdList", {"source_ids": InputDatasetValue(dataset_id="9001")})
    ]
    assert result.result_count == PROTEINS_OF_THE_TYPED_ID
    assert _bound(state) == (
        InputDatasetValue(dataset_id="9001"),
        "stated",
        TYPED_GENE_ID,
        TYPED_GENE_ID,
    )


async def test_the_typed_form_the_overview_shows_carries_the_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)
    state = _state()

    await _bind(
        state,
        {"source_ids": f'{{"type": "input-dataset", "datasetId": "{TYPED_GENE_ID}"}}'},
    )

    assert site.datasets == [[TYPED_GENE_ID]]
    assert _bound(state)[0] == InputDatasetValue(dataset_id="9001")


async def test_the_typed_form_with_a_dataset_id_binds_that_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)
    state = _state()

    await _bind(
        state, {"source_ids": '{"type": "input-dataset", "datasetId": "330713643"}'}
    )

    assert site.datasets == []
    assert site.counted == [
        ("ByIdList", {"source_ids": InputDatasetValue(dataset_id="330713643")})
    ]


async def test_a_typed_numeric_id_is_an_id_and_not_a_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)
    state = _state("Look up the protein with the id 814630.")

    await _bind(state, {"source_ids": "814630"})

    assert site.datasets == [["814630"]]
    assert _bound(state)[1:] == ("stated", "814630", "814630")


async def test_a_re_call_with_the_same_ids_reuses_its_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)
    state = _state()

    await _bind(state, {"source_ids": TYPED_GENE_ID})
    await _bind(state, {"source_ids": [TYPED_GENE_ID]})

    assert site.datasets == [[TYPED_GENE_ID]]
    assert _bound(state)[0] == InputDatasetValue(dataset_id="9001")


async def test_a_form_it_cannot_read_is_refused_naming_the_forms_it_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site: OrthoSite = serve_orthomcl(monkeypatch)
    state = _state()

    with pytest.raises(ModelRetry) as refused:
        await _bind(state, {"source_ids": '{"sourceType": "idList"}'})

    assert refused.value.message == (
        "source_ids takes the ids separated by commas or spaces, or a dataset id "
        'as {"type": "input-dataset", "datasetId": "<id>"}; it read neither in '
        '\'{"sourceType": "idList"}\'. Nothing was recorded.'
    )
    assert site.datasets == []
