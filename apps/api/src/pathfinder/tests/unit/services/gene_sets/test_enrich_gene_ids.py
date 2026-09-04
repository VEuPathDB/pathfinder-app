"""Enrichment of a gene list given by value, with no stored gene set.

Each analysis type is read through the column names its plugin writes, and a
wrong name yields an empty column rather than an error (WDK-ANS-007). The
by-value entry runs the same WDK machinery the stored-set path runs.
"""

from __future__ import annotations

from typing import get_args

import pytest
from assistant_core.platform.types import JSONObject

from pathfinder.domain.strategy.validation import StepValidation
from pathfinder.integrations.veupathdb.wdk_models import (
    NewStepSpec,
    WDKDatasetConfigIdList,
    WDKIdentifier,
    WDKStepAnalysisType,
    WDKStepAnalysisTypeResponse,
    WDKStepTree,
)
from pathfinder.integrations.veupathdb.wdk_parameters import (
    WDKEnumParam,
    WDKNumberParam,
    WDKParameter,
)
from pathfinder.platform.errors import (
    AppError,
    ErrorCode,
    InternalError,
    ValidationError,
)
from pathfinder.services.enrichment import service as enrichment_service
from pathfinder.services.enrichment.types import (
    ALL_ENRICHMENT_ANALYSIS_TYPES,
    BackgroundSource,
    EnrichmentAnalysisType,
    EnrichmentTerm,
)
from pathfinder.services.gene_sets import wdk_helpers
from pathfinder.services.gene_sets.enrichment import (
    MAX_ENRICHMENT_GENE_IDS,
    enrich_gene_ids,
)

_ORGANISM = "Plasmodium falciparum 3D7"

_SHARED_STATS: JSONObject = {
    "bgdGenes": "120",
    "resultGenes": "3",
    "percentInResult": "12.5",
    "foldEnrich": "3.48",
    "oddsRatio": "4.12",
    "pValue": "0.0001",
    "benjamini": "0.002",
    "bonferroni": "0.005",
}

_GO_ROW: JSONObject = {
    "goId": "GO:0004672",
    "goTerm": "protein kinase activity",
    **_SHARED_STATS,
}
_PATHWAY_ROW: JSONObject = {
    "pathwayId": "kegg_pfa00010",
    "pathwayName": "Glycolysis / Gluconeogenesis",
    **_SHARED_STATS,
}
_WORD_ROW: JSONObject = {
    "word": "kinase",
    "pathwayName": "protein kinase, putative",
    **_SHARED_STATS,
}


def _form(analysis_name: str) -> list[WDKParameter]:
    """The parameters an enrichment analysis form offers, with its defaults."""
    params: list[WDKParameter] = [
        WDKEnumParam(
            name="organism",
            type="single-pick-vocabulary",
            initial_display_value=_ORGANISM,
        ),
        WDKNumberParam(name="pValueCutoff", initial_display_value="0.05"),
    ]
    if analysis_name == "go-enrichment":
        params.append(
            WDKEnumParam(
                name="goAssociationsOntologies",
                type="single-pick-vocabulary",
                initial_display_value="Biological Process",
            )
        )
    return params


class _FakeStrategyAPI:
    """Answers the WDK calls the shared enrichment machinery makes."""

    def __init__(self) -> None:
        self.rows: dict[str, list[JSONObject]] = {}
        self.failing: set[str] = set()
        self.datasets: list[list[str]] = []
        self.steps: list[tuple[NewStepSpec, str]] = []
        self.strategies: list[int] = []
        self.deleted: list[int] = []
        self.analyses: list[tuple[str, JSONObject]] = []

    async def create_dataset(self, config: WDKDatasetConfigIdList) -> int:
        self.datasets.append(list(config.source_content.ids))
        return 4242

    async def create_step(self, spec: NewStepSpec, record_type: str) -> WDKIdentifier:
        self.steps.append((spec, record_type))
        return WDKIdentifier(id=101)

    async def create_strategy(
        self,
        *,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        is_internal: bool = False,
    ) -> WDKIdentifier:
        del step_tree, name, description, is_internal
        self.strategies.append(202)
        return WDKIdentifier(id=202)

    async def delete_strategy(self, strategy_id: int) -> None:
        self.deleted.append(strategy_id)

    async def get_step_count(self, step_id: int, user_id: str | None = None) -> int:
        """The step holds the temporary dataset, so its count is the list's."""
        del step_id, user_id
        return len(self.datasets[-1]) if self.datasets else 0

    async def get_analysis_type(
        self, step_id: int, analysis_type: str
    ) -> WDKStepAnalysisTypeResponse:
        del step_id
        return WDKStepAnalysisTypeResponse(
            search_data=WDKStepAnalysisType(
                name=analysis_type,
                display_name=analysis_type,
                parameters=_form(analysis_type),
            ),
            validation=StepValidation(level="DISPLAYABLE", is_valid=True),
        )

    async def run_step_analysis(
        self, *, step_id: int, analysis_type: str, parameters: JSONObject
    ) -> JSONObject:
        del step_id
        self.analyses.append((analysis_type, dict(parameters)))
        if analysis_type in self.failing:
            raise AppError(
                code=ErrorCode.WDK_ERROR, title="Analysis failed", status=500
            )
        return {
            "resultData": self.rows.get(analysis_type, []),
            "downloadPath": "/download",
            "pvalueCutoff": "0.05",
        }


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _FakeStrategyAPI:
    """A site whose WDK calls this fake answers."""
    api = _FakeStrategyAPI()
    monkeypatch.setattr(enrichment_service, "get_strategy_api", lambda site_id: api)
    monkeypatch.setattr(wdk_helpers, "get_strategy_api", lambda site_id: api)
    return api


class TestEachPluginIsReadThroughItsOwnColumns:
    async def test_go_terms_come_from_go_id_and_go_term(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["go-enrichment"] = [_GO_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["go_function"]
        )

        [analysis] = out.analyses
        assert analysis.source_columns.envelope == "resultData"
        assert analysis.source_columns.term_id == "goId"
        assert analysis.source_columns.term_name == "goTerm"
        [term] = analysis.terms
        assert term.term_id == "GO:0004672"
        assert term.term_name == "protein kinase activity"

    async def test_pathway_terms_come_from_pathway_id_and_pathway_name(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["pathway-enrichment"] = [_PATHWAY_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["pathway"]
        )

        [analysis] = out.analyses
        assert analysis.source_columns.envelope == "resultData"
        assert analysis.source_columns.term_id == "pathwayId"
        assert analysis.source_columns.term_name == "pathwayName"
        [term] = analysis.terms
        assert term.term_id == "kegg_pfa00010"
        assert term.term_name == "Glycolysis / Gluconeogenesis"

    async def test_word_terms_come_from_word_and_the_pathway_name_column(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        # WordEnrichmentPlugin.ResultRow.toJson writes json.put("pathwayName",
        # _descrip), so the word description arrives under the pathway key.
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word"]
        )

        [analysis] = out.analyses
        assert analysis.source_columns.envelope == "resultData"
        assert analysis.source_columns.term_id == "word"
        assert analysis.source_columns.term_name == "pathwayName"
        [term] = analysis.terms
        assert term.term_id == "kinase"
        assert term.term_name == "protein kinase, putative"

    @pytest.mark.parametrize(
        ("analysis_type", "expected"),
        [
            ("go_function", ("goId", "goTerm")),
            ("go_process", ("goId", "goTerm")),
            ("go_component", ("goId", "goTerm")),
            ("pathway", ("pathwayId", "pathwayName")),
            ("word", ("word", "pathwayName")),
        ],
    )
    async def test_every_analysis_type_declares_the_columns_it_read(
        self,
        wdk: _FakeStrategyAPI,
        analysis_type: EnrichmentAnalysisType,
        expected: tuple[str, str],
    ) -> None:
        wdk.rows["go-enrichment"] = [_GO_ROW]
        wdk.rows["pathway-enrichment"] = [_PATHWAY_ROW]
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), [analysis_type]
        )

        [analysis] = out.analyses
        columns = analysis.source_columns
        assert (columns.term_id, columns.term_name) == expected


class TestAWrongColumnNameIsSilent:
    async def test_the_word_description_under_descrip_reads_as_an_empty_name(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        # There is no `descrip` key on the wire. A client reading it gets a
        # term with no name, not a failure.
        row = {k: v for k, v in _WORD_ROW.items() if k != "pathwayName"}
        wdk.rows["word-enrichment"] = [{**row, "descrip": "protein kinase, putative"}]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word"]
        )

        [analysis] = out.analyses
        [term] = analysis.terms
        assert term.term_id == "kinase"
        assert term.term_name == ""

    @pytest.mark.parametrize(
        ("analysis_type", "wdk_name", "row", "renamed"),
        [
            ("go_function", "go-enrichment", _GO_ROW, "goId"),
            ("go_function", "go-enrichment", _GO_ROW, "goTerm"),
            ("pathway", "pathway-enrichment", _PATHWAY_ROW, "pathwayId"),
            ("pathway", "pathway-enrichment", _PATHWAY_ROW, "pathwayName"),
            ("word", "word-enrichment", _WORD_ROW, "word"),
        ],
    )
    async def test_a_renamed_identity_column_yields_no_terms(
        self,
        wdk: _FakeStrategyAPI,
        analysis_type: EnrichmentAnalysisType,
        wdk_name: str,
        row: JSONObject,
        renamed: str,
    ) -> None:
        broken = {k: v for k, v in row.items() if k != renamed}
        wdk.rows[wdk_name] = [{**broken, f"{renamed}_": row[renamed]}]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), [analysis_type]
        )

        [analysis] = out.analyses
        assert analysis.terms == []
        assert analysis.error is None


class TestTheGeneListIsBounded:
    async def test_a_list_over_the_cap_is_refused_before_any_wdk_call(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        ids = [f"PF3D7_{i:07d}" for i in range(MAX_ENRICHMENT_GENE_IDS + 1)]

        with pytest.raises(ValidationError) as err:
            await enrich_gene_ids("plasmodb", ids, BackgroundSource())

        assert err.value.detail is not None
        assert "gene_ids" in err.value.detail
        assert str(MAX_ENRICHMENT_GENE_IDS) in err.value.detail
        assert wdk.datasets == []

    async def test_a_list_at_the_cap_is_accepted(self, wdk: _FakeStrategyAPI) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]
        ids = [f"PF3D7_{i:07d}" for i in range(MAX_ENRICHMENT_GENE_IDS)]

        out = await enrich_gene_ids("plasmodb", ids, BackgroundSource(), ["word"])

        assert out.gene_count == MAX_ENRICHMENT_GENE_IDS

    async def test_an_empty_list_is_refused_naming_the_field(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        with pytest.raises(ValidationError) as err:
            await enrich_gene_ids("plasmodb", ["  ", ""], BackgroundSource())

        assert err.value.detail is not None
        assert "gene_ids" in err.value.detail
        assert wdk.datasets == []

    async def test_a_repeated_id_is_one_gene(self, wdk: _FakeStrategyAPI) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        out = await enrich_gene_ids(
            "plasmodb",
            ["PF3D7_0100100", " PF3D7_0100100 ", "PF3D7_0200200"],
            BackgroundSource(),
            ["word"],
        )

        assert out.gene_count == 2
        assert wdk.datasets == [["PF3D7_0100100", "PF3D7_0200200"]]


class TestTheByValuePathRunsTheStoredSetMachinery:
    async def test_the_genes_become_a_locus_tag_step_over_a_wdk_dataset(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word"]
        )

        [(spec, record_type)] = wdk.steps
        assert spec.search_name == "GeneByLocusTag"
        assert record_type == "transcript"
        assert spec.search_config.parameters["ds_gene_ids"] == "4242"

    async def test_the_temporary_strategy_is_deleted(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word"]
        )

        assert wdk.deleted == wdk.strategies

    async def test_the_terms_are_the_shared_enrichment_term_model(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        # One parser and one term model serve both entry points.
        wdk.rows["go-enrichment"] = [_GO_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["go_process"]
        )

        assert all(isinstance(t, EnrichmentTerm) for t in out.analyses[0].terms)

    async def test_the_p_value_is_the_one_wdk_reported(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        # The plugin runs Fisher's exact test. Nothing recomputes it here.
        wdk.rows["go-enrichment"] = [_GO_ROW]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["go_process"]
        )

        [term] = out.analyses[0].terms
        assert term.p_value == pytest.approx(0.0001)
        assert term.fdr == pytest.approx(0.002)
        assert term.bonferroni == pytest.approx(0.005)

    async def test_an_unbounded_ratio_is_none(self, wdk: _FakeStrategyAPI) -> None:
        wdk.rows["go-enrichment"] = [{**_GO_ROW, "foldEnrich": "Infinity"}]

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["go_process"]
        )

        [term] = out.analyses[0].terms
        assert term.fold_enrichment is None

    async def test_every_analysis_type_runs_by_default(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        out = await enrich_gene_ids("plasmodb", ["PF3D7_0100100"], BackgroundSource())

        ran = [a.analysis_type for a in out.analyses]
        assert set(ran) == set(ALL_ENRICHMENT_ANALYSIS_TYPES)


class TestTheBackgroundIsTheOrganismTheCallerNamed:
    async def test_the_named_organism_is_sent_as_a_vocabulary_value(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        await enrich_gene_ids(
            "plasmodb",
            ["PF3D7_0100100"],
            BackgroundSource(organism="Plasmodium vivax P01"),
            ["word"],
        )

        [(_, params)] = wdk.analyses
        assert params["organism"] == '["Plasmodium vivax P01"]'

    async def test_no_named_organism_keeps_the_analysis_form_default(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word"]
        )

        [(_, params)] = wdk.analyses
        assert params["organism"] == f'["{_ORGANISM}"]'

    async def test_the_background_is_reported_with_the_result(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]

        out = await enrich_gene_ids(
            "plasmodb",
            ["PF3D7_0100100"],
            BackgroundSource(organism=_ORGANISM),
            ["word"],
        )

        assert out.background.organism == _ORGANISM
        assert out.site_id == "plasmodb"


class TestAFailedAnalysisIsNamed:
    async def test_one_failure_is_reported_on_its_own_analysis(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.rows["word-enrichment"] = [_WORD_ROW]
        wdk.failing = {"pathway-enrichment"}

        out = await enrich_gene_ids(
            "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word", "pathway"]
        )

        by_type = {a.analysis_type: a for a in out.analyses}
        assert by_type["word"].error is None
        assert by_type["pathway"].error is not None
        assert by_type["pathway"].terms == []

    async def test_every_analysis_failing_is_an_error_not_an_empty_result(
        self, wdk: _FakeStrategyAPI
    ) -> None:
        wdk.failing = {"word-enrichment", "pathway-enrichment"}

        with pytest.raises(InternalError):
            await enrich_gene_ids(
                "plasmodb", ["PF3D7_0100100"], BackgroundSource(), ["word", "pathway"]
            )


def test_the_declared_analysis_types_are_the_ones_the_literal_allows() -> None:
    assert get_args(EnrichmentAnalysisType.__value__) == ALL_ENRICHMENT_ANALYSIS_TYPES
