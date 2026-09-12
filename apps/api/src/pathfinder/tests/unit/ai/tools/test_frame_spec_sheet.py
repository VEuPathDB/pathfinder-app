"""The parameter sheet a params-less ``set_criterion`` pins, and what a bound
criterion records: the search registry and the values FRAME assumed."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import VocabOption, WDKVocabTerm
from veupathdb.wdk import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)
from veupathdb_mcp.catalog import FilterFieldInfo, ParameterInfo

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.tools.standalone._frame_proposals import DeclaredAssumption
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult
from pathfinder.domain.strategy.operational_spec import AssumedValue
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    Proposals,
    bind,
    genes_by_text,
    param_info,
    serve_definition,
    serve_params,
    serve_search,
)


def genes_by_text_wdk() -> list[WDKParameter]:
    """GenesByText as WDK defines it, matching ``genes_by_text`` param for param."""
    parameters: list[WDKParameter] = [
        WDKStringParam(
            name="text_expression", display_name="Text", allow_empty_value=False
        ),
        WDKEnumParam(
            name="text_search_organism",
            display_name="Organism",
            type="multi-pick-vocabulary",
            allow_empty_value=False,
            vocabulary=[
                WDKVocabTerm(("Plasmodium", "Plasmodium", None)),
                WDKVocabTerm(("Plasmodium falciparum 3D7", "P. falciparum 3D7", None)),
            ],
        ),
        WDKStringParam(
            name="document_type",
            display_name="Document type",
            allow_empty_value=True,
            initial_display_value="gene",
        ),
        WDKEnumParam(
            name="text_fields",
            display_name="Fields",
            type="multi-pick-vocabulary",
            allow_empty_value=True,
            initial_display_value='["product", "Notes"]',
            vocabulary=[
                WDKVocabTerm(("product", "product", None)),
                WDKVocabTerm(("Notes", "Notes", None)),
            ],
        ),
    ]
    return parameters


def serve_genes_by_text_definition(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return serve_definition(
        monkeypatch,
        genes_by_text_wdk(),
        display_name="Gene Text Search",
        description="Search gene text.",
    )


async def sheet_call(
    state: AgentToolState, criterion_id: str = "c1"
) -> SetCriterionResult:
    return await bind(state, "GenesByText", criterion_id=criterion_id)


class TestTheSheetComesBackFromSetCriterion:
    """A call with no ``params`` pins the sheet and records nothing.

    The sheet and the registry entry come from ONE read of the search, so they
    can never disagree about which parameters exist.
    """

    @pytest.mark.asyncio
    async def test_no_params_pins_one_entry_per_visible_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = serve_genes_by_text_definition(monkeypatch)

        def _explode(_context: dict[str, str]) -> list[ParameterInfo]:
            message = "the sheet must not fetch the params separately"
            raise AssertionError(message)

        serve_params(monkeypatch, _explode)
        st = AgentToolState()

        result = await sheet_call(st)

        sheet = st.open_sheets["c1"]
        assert [entry.name for entry in sheet.entries] == [
            "text_expression",
            "text_search_organism",
            "document_type",
            "text_fields",
        ]
        organism = next(e for e in sheet.entries if e.name == "text_search_organism")
        assert [o.value for o in organism.vocabulary] == [
            "Plasmodium",
            "Plasmodium falciparum 3D7",
        ]
        assert result.resolved_params == {}
        assert st.operational_spec_draft.criteria == [], "nothing is recorded yet"
        assert reads == ["GenesByText"], "one read serves the sheet and the registry"

    @pytest.mark.asyncio
    async def test_no_params_registers_the_search_from_the_same_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # BUILD's discovery gate reads the registry, so a criterion framed
        # without an overview call must still register its search.
        serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        result = await sheet_call(st)

        overview = st.get_overview("GenesByText")
        assert overview is not None
        assert overview.record_type == "transcript"
        assert overview.parameter_names == list(result.params_template)
        assert overview.required_params == ["text_expression", "text_search_organism"]

    @pytest.mark.asyncio
    async def test_the_template_is_the_params_object_to_send_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A template the model copies leaves it no parameter name to invent.
        serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        result = await sheet_call(st)

        assert list(result.params_template) == [
            e.name for e in st.open_sheets["c1"].entries
        ]
        assert set(result.params_template.values()) == {None}

    @pytest.mark.asyncio
    async def test_an_already_registered_search_keeps_its_entry_and_gets_a_sheet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()
        st.register_search(
            "GenesByText",
            SearchOverview(
                search_name="GenesByText",
                display_name="Read by the overview tool",
                record_type="transcript",
                description="",
                parameter_names=["text_expression"],
                required_params=[],
            ),
        )

        result = await sheet_call(st)

        assert result.sheet_pinned, "the sheet is still pinned"
        assert reads == ["GenesByText"], "still exactly one read"
        overview = st.get_overview("GenesByText")
        assert overview is not None
        assert overview.display_name == "Read by the overview tool"


class TestASecondSheetIsTheSamePin:
    """The pin holds one sheet per criterion, so a re-open replaces it."""

    @pytest.mark.asyncio
    async def test_the_second_sheet_keeps_the_params_and_the_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        first = await sheet_call(st)
        second = await sheet_call(st)

        assert list(second.params_template) == list(first.params_template)
        assert list(st.open_sheets) == ["c1"]
        entries = st.open_sheets["c1"].entries
        organism = next(e for e in entries if e.name == "text_search_organism")
        assert [o.value for o in organism.vocabulary] == [
            "Plasmodium",
            "Plasmodium falciparum 3D7",
        ]
        assert organism.required is True
        assert organism.is_tree is False
        text_fields = next(e for e in entries if e.name == "text_fields")
        assert text_fields.default == '["product", "Notes"]'

    @pytest.mark.asyncio
    async def test_another_criterion_on_the_same_search_pins_its_own_sheet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two criteria over one search are two separate questions.
        serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        await sheet_call(st, criterion_id="c1")
        await sheet_call(st, criterion_id="c2")

        entries = st.open_sheets["c2"].entries
        organism = next(e for e in entries if e.name == "text_search_organism")
        assert [o.value for o in organism.vocabulary] == [
            "Plasmodium",
            "Plasmodium falciparum 3D7",
        ]


class TestTheParamsPathRegistersTheSearch:
    """BUILD reads the discovery gate, so every bound criterion needs an entry,
    which is read once and then reused."""

    @pytest.mark.asyncio
    async def test_a_params_first_call_registers_the_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)
        reads = serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        await bind(st, "GenesByText", dict(KINASE_PARAMS))

        overview = st.get_overview("GenesByText")
        assert overview is not None
        assert overview.record_type == "transcript"
        assert overview.parameter_names == [
            "text_expression",
            "text_search_organism",
            "document_type",
            "text_fields",
        ]
        assert reads == ["GenesByText"]

    @pytest.mark.asyncio
    async def test_a_registered_search_is_not_read_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)
        reads = serve_genes_by_text_definition(monkeypatch)
        st = AgentToolState()

        await sheet_call(st)
        await bind(st, "GenesByText", dict(KINASE_PARAMS))

        assert reads == ["GenesByText"], "the sheet's own read serves the registry"


class TestEveryVisibleRequiredParamIsDecided:
    @pytest.mark.asyncio
    async def test_a_missing_required_param_is_a_retry_naming_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)
        st = AgentToolState()

        with pytest.raises(ModelRetry) as info:
            await bind(st, "GenesByText", {"text_expression": "kinase"})

        assert "text_search_organism" in str(info.value)
        assert st.operational_spec_draft.criteria == []

    @pytest.mark.asyncio
    async def test_null_binds_the_default_and_discloses_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)

        result = await bind(AgentToolState(), "GenesByText", dict(KINASE_PARAMS))

        assert "document_type" in result.defaulted_params
        assert result.resolved_params["text_expression"] == "kinase"
        assert result.resolved_params["text_search_organism"] == '["Plasmodium"]'


_SAMPLE_WINDOWS = [
    VocabOption(value="17-30h", display="17-30 hours"),
    VocabOption(value="1-16h", display="1-16 hours"),
]
_FILTER_FIELD = FilterFieldInfo(
    term="Sample type", display="Sample type", type="string", values=["a", "b"]
)
_DERISI = "GenesByMicroarrayDerisi"
_TROPHOZOITE = DeclaredAssumption(
    param_name="samples_percentile_generic",
    value="17-30h",
    reason="the request says trophozoite and this window covers 17-30 hours",
)
_STATED: Proposals = {
    "min_expression_percentile": "90",
    "samples_percentile_generic": "17-30h",
    "ref_samples": "Sample type=a",
    "comp_samples": "Sample type=b",
}
_REFUSED_ASSUMPTIONS: list[
    tuple[Proposals, list[DeclaredAssumption], tuple[str, ...]]
] = [
    (
        dict(_STATED),
        [
            DeclaredAssumption(
                param_name="comp_samples", value="Sample type=b", reason="sensible"
            )
        ],
        ("comp_samples", "contrast"),
    ),
    (
        dict(_STATED),
        [
            DeclaredAssumption(
                param_name="samples_percentile", value="17-30h", reason="typo"
            )
        ],
        ("samples_percentile",),
    ),
    (
        {**_STATED, "samples_percentile_generic": None},
        [_TROPHOZOITE],
        ("samples_percentile_generic",),
    ),
]


def _derisi_params(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info("min_expression_percentile"),
        param_info(
            "samples_percentile_generic",
            "single-pick-vocabulary",
            vocab_leaves=_SAMPLE_WINDOWS,
        ),
        param_info("ref_samples", "filter", filter_fields=[_FILTER_FIELD]),
        param_info("comp_samples", "filter", filter_fields=[_FILTER_FIELD]),
    ]


class TestADeclaredAssumptionIsRecorded:
    """A value FRAME chose that the request does not state is recorded on the
    criterion, not narrated."""

    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        serve_search(monkeypatch, _derisi_params)

    async def _bind(
        self,
        state: AgentToolState,
        params: Proposals,
        assumed: list[DeclaredAssumption],
    ) -> None:
        await bind(
            state,
            _DERISI,
            params,
            text="top 10 percent of trophozoite expression",
            assumed=assumed,
        )

    @pytest.mark.asyncio
    async def test_a_declared_assumption_is_recorded_on_the_criterion(self) -> None:
        state = AgentToolState()

        await self._bind(state, dict(_STATED), [_TROPHOZOITE])

        [criterion] = state.operational_spec_draft.criteria
        assert criterion.assumptions == [
            AssumedValue(
                param_name=_TROPHOZOITE.param_name,
                value=_TROPHOZOITE.value,
                reason=_TROPHOZOITE.reason,
            )
        ]

    def test_the_declared_shape_carries_no_fold_record(self) -> None:
        """``carried_from`` is the fold's, so the sheet the model fills has none."""
        declared = set(DeclaredAssumption.model_json_schema()["properties"])

        assert declared == {"paramName", "value", "reason"}
        assert "carriedFrom" in AssumedValue.model_json_schema()["properties"]

    @pytest.mark.asyncio
    async def test_a_criterion_without_assumptions_records_none(self) -> None:
        state = AgentToolState()

        await self._bind(state, dict(_STATED), [])

        [criterion] = state.operational_spec_draft.criteria
        assert criterion.assumptions == []

    @pytest.mark.parametrize(("params", "assumed", "fragments"), _REFUSED_ASSUMPTIONS)
    @pytest.mark.asyncio
    async def test_a_refused_assumption_names_the_parameter(
        self,
        params: Proposals,
        assumed: list[DeclaredAssumption],
        fragments: tuple[str, ...],
    ) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as info:
            await self._bind(state, params, assumed)

        message = str(info.value)
        for fragment in fragments:
            assert fragment in message
        assert state.operational_spec_draft.criteria == []
