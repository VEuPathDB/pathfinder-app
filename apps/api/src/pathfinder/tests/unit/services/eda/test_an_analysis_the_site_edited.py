"""An analysis the site's own EDA app edited: a pass compute beside the comparison."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import StringValue
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaComparator,
    EdaComputation,
    EdaDifferentialExpressionComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaLabeledRange,
    EdaVariableSpec,
)

from pathfinder.ai.tools.standalone._eda_step_guard import (
    refuse_a_direction_without_a_volcano,
)
from pathfinder.domain.eda_parts import EdaComparison, EdaComputeSummary
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.services.eda.binding import read_analysis, read_analysis_state
from pathfinder.services.eda.comparison import apply_computation
from pathfinder.services.eda.compute import (
    DEFAULT_VOLCANO_CUT,
    VolcanoThresholds,
    analysis_comparison,
    stored_volcano_cut,
)
from pathfinder.services.eda.export import eda_step_request, exported_analysis
from pathfinder.services.eda.gene_subset import (
    NoGeneSubsetError,
    refuse_a_subset_that_selects_no_genes,
)
from pathfinder.tests._support.eda_wire import (
    DE_ENTITY_SIZES,
    PHENOTYPE_DATASET,
    AnalysisStore,
    eda_transport,
    fixture,
    wire_eda,
)

_RECORDED = fixture("analysis_detail_pass_and_de")
_ANALYSIS = "uoZgkI9"
_DATASET = "DS_e973eadd57"
_PASS = "k3x9q"
_DE = "m7p2d"
_VOLCANO = "7e2c4a91-3b5d-4f60-8a1e-9c0d2b4f6a85"
_COUNTS_ENTITY = "ENT_fd574cd6"

# The recorded deployment grants no DE dataset, so the wire serves the DE
# study under the phenotype dataset's permission entry.
_WIRED_DATASET = PHENOTYPE_DATASET
_WIRED_STUDY = "STUDY_53f554ec6a"


def _recorded(computation_id: str) -> dict[str, Any]:
    computations: list[dict[str, Any]] = _RECORDED["descriptor"]["computations"]
    return next(c for c in computations if c["computationId"] == computation_id)


def _pass_only() -> EdaAnalysisDetail:
    """The recorded analysis before the researcher added the comparison."""
    raw = {
        **_RECORDED,
        "numComputations": 1,
        "descriptor": {
            **_RECORDED["descriptor"],
            "computations": [_recorded(_PASS)],
        },
    }
    return EdaAnalysisDetail.model_validate(raw)


def _with_computations(*computations: dict[str, Any]) -> EdaAnalysisDetail:
    """The recorded analysis, holding these stored computations instead."""
    raw = {
        **_RECORDED,
        "numComputations": len(computations),
        "descriptor": {**_RECORDED["descriptor"], "computations": list(computations)},
    }
    return EdaAnalysisDetail.model_validate(raw)


# A pass compute carrying keys PathFinder does not model, as a later app may store.
_PASS_WITH_UNKNOWN_KEYS = {
    **_recorded(_PASS),
    "descriptor": {"type": "pass", "configuration": {"madeUp": [1, "a", None]}},
    "madeUpComputationKey": {"kept": True},
}

# The recorded comparison, whose volcano stores no direction and one plot setting.
_DE_WITHOUT_DIRECTION = {
    **_recorded(_DE),
    "visualizations": [
        {
            "visualizationId": _VOLCANO,
            "descriptor": {
                "type": "volcanoplot",
                "configuration": {
                    "effectSizeThreshold": 1,
                    "significanceThreshold": 0.05,
                    "showLegend": True,
                },
            },
        }
    ],
}

# The body of the comparison PathFinder builds, with every default it carries.
_SWAPPED_BODY = {
    "computationId": "c1",
    "descriptor": {
        "type": "differentialexpression",
        "configuration": {
            "identifierVariable": {
                "entityId": _COUNTS_ENTITY,
                "variableId": "VEUPATHDB_GENE_ID",
            },
            "valueVariable": {
                "entityId": _COUNTS_ENTITY,
                "variableId": "SEQUENCE_READ_COUNT_ANTISENSE",
            },
            "comparator": {
                "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
                "groupA": [{"label": "febrile"}],
                "groupB": [{"label": "normal"}],
            },
            "differentialExpressionMethod": "DESeq",
            "pValueFloor": "1e-200",
        },
    },
    "visualizations": [],
}


def _swapped() -> EdaDifferentialExpressionComputation:
    """The recorded comparison with its two groups exchanged."""
    descriptor = EdaDifferentialExpressionDescriptor(
        configuration=EdaDifferentialExpressionConfig(
            identifier_variable=EdaVariableSpec(
                entity_id=_COUNTS_ENTITY, variable_id="VEUPATHDB_GENE_ID"
            ),
            value_variable=EdaVariableSpec(
                entity_id=_COUNTS_ENTITY, variable_id="SEQUENCE_READ_COUNT_ANTISENSE"
            ),
            comparator=EdaComparator(
                variable=EdaVariableSpec(
                    entity_id="ENT_8151325d", variable_id="VAR_081ab087"
                ),
                group_a=[EdaLabeledRange(label="febrile")],
                group_b=[EdaLabeledRange(label="normal")],
            ),
        )
    )
    return EdaDifferentialExpressionComputation(
        computation=EdaComputation(computation_id="c1", descriptor=descriptor),
        descriptor=descriptor,
    )


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(reset)


def _wired(monkeypatch: pytest.MonkeyPatch, detail: EdaAnalysisDetail) -> AnalysisStore:
    store = AnalysisStore(detail=detail)
    wire_eda(
        monkeypatch,
        eda_transport(
            study_id=_WIRED_STUDY,
            study_fixture="study_detail_de",
            store=store,
            entity_sizes=DE_ENTITY_SIZES,
        ),
    )
    return store


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> AnalysisStore:
    return _wired(monkeypatch, EdaAnalysisDetail.model_validate(_RECORDED))


def _bound() -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=_WIRED_DATASET,
        analysis_id=_ANALYSIS,
        revision=3,
    )


async def test_the_state_names_the_comparison_by_the_study_names(
    recorded: AnalysisStore,
) -> None:
    del recorded
    detail = await read_analysis("plasmodb", analysis_id=_ANALYSIS)

    state = await read_analysis_state(bound=_bound(), analysis=detail)

    assert state.num_computations == 2
    assert state.compute == EdaComputeSummary(
        method="DESeq",
        identifier_variable="Gene",
        value_variable="Antisense Count",
        comparator_variable="temperature_condition",
        group_a=["normal"],
        group_b=["febrile"],
    )


async def test_the_state_of_an_analysis_with_no_comparison_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, _pass_only())
    detail = await read_analysis("plasmodb", analysis_id=_ANALYSIS)

    state = await read_analysis_state(bound=_bound(), analysis=detail)

    assert (state.num_computations, state.compute) == (1, None)


async def test_every_read_takes_the_document_the_site_holds_now(
    recorded: AnalysisStore,
) -> None:
    """The site edits the shared document, and the next read carries the edit."""
    before = await read_analysis("plasmodb", analysis_id=_ANALYSIS)
    recorded.detail = _with_computations(_recorded(_PASS), _SWAPPED_BODY)

    after = await read_analysis("plasmodb", analysis_id=_ANALYSIS)
    state = await read_analysis_state(bound=_bound(), analysis=after)

    assert analysis_comparison(before) == EdaComparison(
        group_a=["normal"], group_b=["febrile"]
    )
    assert state.compute is not None
    assert (state.compute.group_a, state.compute.group_b) == (["febrile"], ["normal"])
    assert state.compute.value_variable == "Antisense Count"


def test_the_comparison_is_the_differential_expression() -> None:
    detail = EdaAnalysisDetail.model_validate(_RECORDED)
    assert analysis_comparison(detail) == EdaComparison(
        group_a=["normal"], group_b=["febrile"]
    )


def test_the_figure_takes_the_cut_the_comparison_stores() -> None:
    """A cut set in the site's volcano cell is the cut the tab draws."""
    stored = {
        **_recorded(_DE),
        "visualizations": [
            {
                "visualizationId": _VOLCANO,
                "descriptor": {
                    "type": "volcanoplot",
                    "configuration": {
                        "effectSizeThreshold": 2,
                        "significanceThreshold": 0.01,
                        "effectDirection": "upOnly",
                    },
                },
            }
        ],
    }

    cut = stored_volcano_cut(_with_computations(_recorded(_PASS), stored))

    assert cut == VolcanoThresholds(
        effect_size_threshold=2.0,
        significance_threshold=0.01,
        effect_direction="upOnly",
    )


def test_a_comparison_with_no_stored_volcano_takes_the_default_cut() -> None:
    bare = {**_recorded(_DE), "visualizations": []}

    cut = stored_volcano_cut(_with_computations(_recorded(_PASS), bare))

    assert cut == DEFAULT_VOLCANO_CUT
    assert (cut.effect_size_threshold, cut.significance_threshold) == (1.0, 0.05)
    assert cut.effect_direction == "upAndDown"


def test_a_compute_export_puts_the_comparison_first_and_keeps_the_pass() -> None:
    """The bridge plugin reads the first computation and its first visualization."""
    detail = EdaAnalysisDetail.model_validate(_RECORDED)

    request = eda_step_request(
        detail,
        dataset_id=_DATASET,
        effect_size_threshold=2.0,
        significance_threshold=0.01,
    )

    spec = json.loads(request.eda_analysis_spec)
    computations = spec["descriptor"]["computations"]
    assert [c["computationId"] for c in computations] == [_DE, _PASS]
    assert computations[1] == _recorded(_PASS)
    volcano = computations[0]["visualizations"]
    assert [v["visualizationId"] for v in volcano] == [_VOLCANO]
    assert volcano[0]["descriptor"]["configuration"] == {
        "effectSizeThreshold": 2.0,
        "significanceThreshold": 0.01,
        "effectDirection": "upAndDown",
        "markerBodyOpacity": 0.5,
    }
    binding = exported_analysis(
        AnalysisKind.COMPUTE,
        {name: StringValue(value=v) for name, v in request.wdk_parameters().items()},
    )
    assert binding is not None
    assert (
        binding.effect_size_threshold,
        binding.significance_threshold,
        binding.effect_direction,
    ) == (2.0, 0.01, "upAndDown")


@pytest.mark.parametrize(
    ("comparison", "kept"),
    [
        (_DE_WITHOUT_DIRECTION, {"showLegend": True}),
        ({**_recorded(_DE), "visualizations": []}, {}),
    ],
    ids=["a stored volcano with no direction", "no stored volcano"],
)
def test_an_exported_volcano_states_the_whole_cut(
    comparison: dict[str, Any], kept: dict[str, Any]
) -> None:
    """The bridge plugin reads all three keys from the exported configuration."""
    request = eda_step_request(
        _with_computations(_recorded(_PASS), comparison),
        dataset_id=_DATASET,
        effect_size_threshold=2.0,
        significance_threshold=0.01,
    )

    spec = json.loads(request.eda_analysis_spec)
    [volcano] = spec["descriptor"]["computations"][0]["visualizations"]
    assert volcano["descriptor"]["configuration"] == {
        "effectSizeThreshold": 2.0,
        "significanceThreshold": 0.01,
        "effectDirection": "upAndDown",
        **kept,
    }


def test_a_subset_export_keeps_the_site_order_and_carries_no_cut() -> None:
    detail = EdaAnalysisDetail.model_validate(_RECORDED)

    request = eda_step_request(detail, dataset_id=_DATASET)

    spec = json.loads(request.eda_analysis_spec)
    assert spec["descriptor"]["computations"] == [_recorded(_PASS), _recorded(_DE)]
    binding = exported_analysis(
        AnalysisKind.SUBSET,
        {name: StringValue(value=v) for name, v in request.wdk_parameters().items()},
    )
    assert binding is not None
    assert binding.significance_threshold is None


async def test_a_compute_write_replaces_only_the_comparison(
    recorded: AnalysisStore,
) -> None:
    await apply_computation(
        "plasmodb",
        analysis_id=_ANALYSIS,
        dataset_id=_WIRED_DATASET,
        computation=_swapped(),
    )

    [body] = recorded.patched
    assert body["descriptor"]["computations"] == [_recorded(_PASS), _SWAPPED_BODY]


async def test_a_compute_write_keeps_the_keys_a_pass_stores_that_are_not_modelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wired(
        monkeypatch, _with_computations(_PASS_WITH_UNKNOWN_KEYS, _recorded(_DE))
    )

    await apply_computation(
        "plasmodb",
        analysis_id=_ANALYSIS,
        dataset_id=_WIRED_DATASET,
        computation=_swapped(),
    )

    [body] = store.patched
    assert body["descriptor"]["computations"] == [
        _PASS_WITH_UNKNOWN_KEYS,
        _SWAPPED_BODY,
    ]


async def test_a_compute_write_appends_the_comparison_beside_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wired(monkeypatch, _pass_only())

    await apply_computation(
        "plasmodb",
        analysis_id=_ANALYSIS,
        dataset_id=_WIRED_DATASET,
        computation=_swapped(),
    )

    [body] = store.patched
    computations = body["descriptor"]["computations"]
    assert [c["computationId"] for c in computations] == [_PASS, "c1"]
    assert computations[0] == _recorded(_PASS)


def test_a_direction_needs_a_comparison_and_a_pass_is_none() -> None:
    with pytest.raises(ModelRetry) as refusal:
        refuse_a_direction_without_a_volcano(
            _pass_only(), effect_direction="upOnly", has_thresholds=True
        )
    assert "the open analysis holds 0 comparisons" in str(refusal.value)


def test_a_direction_beside_a_pass_and_a_comparison_passes() -> None:
    refuse_a_direction_without_a_volcano(
        EdaAnalysisDetail.model_validate(_RECORDED),
        effect_direction="upOnly",
        has_thresholds=True,
    )


async def test_a_subset_export_counts_one_comparison_not_two(
    recorded: AnalysisStore,
) -> None:
    del recorded
    with pytest.raises(NoGeneSubsetError) as refusal:
        await refuse_a_subset_that_selects_no_genes(
            "plasmodb",
            dataset_id=_WIRED_DATASET,
            analysis=EdaAnalysisDetail.model_validate(_RECORDED),
        )
    assert refusal.value.detail == (
        "The analysis holds no filter and 1 comparison, and no filter on pfal3D7 "
        "htseq counts. A step holds genes, and a subset of another entity "
        "selects no genes, so nothing was written. Export the genes that pass a "
        "volcano cut, or add a filter on pfal3D7 htseq counts."
    )
