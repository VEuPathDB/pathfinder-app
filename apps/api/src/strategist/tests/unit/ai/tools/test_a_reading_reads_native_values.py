"""A reading, an options read and a proposed change read native values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import JsonValue, TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    ParamValue,
    from_wire,
)
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import (
    BoundValues,
    ParameterInfo,
    ResolveContext,
    read_under_parents,
)

from strategist.ai.explore import explore_tools
from strategist.ai.explore.explore_tools import propose_readings
from strategist.ai.lead.proposal import AddCriterionChange, SetValuesChange
from strategist.ai.tools.standalone import (
    _stated_values,
    catalog_discovery,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.experiment.reading_count import (
    ProposedReading,
    ProposedReadingDraft,
)
from strategist.services.experiment.variant_comparison import VariantSpec
from strategist.tests._support.bound_values import bound
from strategist.tests._support.explore_turns import serve_recorded_readings
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.record_classes import recorded_searches
from strategist.tests._support.recorded_searches import (
    client_search,
    serve_stated_reads,
)
from strategist.tests._support.run_context import lead_run_context
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
)
from strategist.tests.unit.ai.tools.conftest import patch_search_details, wdk_param

_PF = "Plasmodium falciparum 3D7"
_VARIANTS = "GenesByVariantCharacteristics"
_TREE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_DECLARATION: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
CAPTURED = "captured"
COUNTED = "counted"
READ = "read"
_AT_LEAST_SIX: JsonValue = [{"field": "total_variants", "value": {"min": 6}}]


@pytest.fixture
def stated_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_stated_reads(monkeypatch, list(recorded_searches().values()))


def _taxon_graph() -> StrategyGraph:
    return graph_with(StrategyStepNode(id="step_t", search_name="GenesByTaxon"))


def _variant_plan(stats: JsonValue) -> ProposedReadingDraft:
    return ProposedReadingDraft.model_validate(
        {
            "title": "Genes with many variants",
            "searches": [
                {
                    "label": "variants",
                    "searchName": _VARIANTS,
                    "parameters": {
                        "organism_select_none": [_PF],
                        "gene_variant_stats": stats,
                    },
                }
            ],
        }
    )


def _counted(monkeypatch: pytest.MonkeyPatch) -> list[VariantSpec]:
    counted: list[VariantSpec] = []

    async def _count(
        site_id: str,
        proposal: ProposedReading,
        specs: Sequence[VariantSpec],
        spec: OperationalSpec,
    ) -> object:
        del site_id, proposal, spec
        counted.extend(specs)
        raise ModelRetry(COUNTED)

    monkeypatch.setattr(explore_tools, "run_reading_count", _count)
    return counted


class TestAReadingReadsNativeValues:
    async def test_a_filter_statement_counts_with_its_range_clause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_recorded_readings(monkeypatch)
        counted = _counted(monkeypatch)

        with pytest.raises(ModelRetry, match="counted"):
            await propose_readings(lead_run_context(), [_variant_plan(_AT_LEAST_SIX)])

        [clause] = FilterValue.model_validate(
            counted[0].parameters["gene_variant_stats"].model_dump()
        ).filters
        assert clause.model_dump(by_alias=True) == {
            "field": "total_variants",
            "type": "number",
            "isRange": True,
            "includeUnknown": False,
            "value": {"min": 6.0, "max": None},
        }

    async def test_the_filter_shorthand_is_refused_before_any_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_recorded_readings(monkeypatch)
        counted = _counted(monkeypatch)

        with pytest.raises(ModelRetry, match="gene_variant_stats takes a list of"):
            await propose_readings(
                lead_run_context(), [_variant_plan("total_variants<=5")]
            )

        assert counted == []

    async def test_a_shape_fault_is_refused_before_any_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_recorded_readings(monkeypatch)
        counted = _counted(monkeypatch)
        plan = ProposedReadingDraft.model_validate(
            {
                "title": "Genes with a signal peptide",
                "searches": [
                    {
                        "label": "peptides",
                        "searchName": "GenesWithSignalPeptide",
                        "parameters": {
                            "organism": _PF,
                            "signalp_version": "SignalP-7.0",
                        },
                    }
                ],
            }
        )

        with pytest.raises(ModelRetry) as refused:
            await propose_readings(lead_run_context(), [plan])

        assert "organism takes a list" in refused.value.message
        assert counted == []


_VIVAX = "Plasmodium vivax P01"
_PERU = "WGS of Patient Isolates from Peru"


def _snps_under_their_organism(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Serve the recorded NgsSnps declarations under the organism each read
    sends, and record every context a declaration read was asked under."""
    under = {
        '["Plasmodium falciparum 3D7"]': client_search("search_genes_by_ngs_snps"),
        f'["{_VIVAX}"]': client_search(
            "search_genes_by_ngs_snps_under_another_organism"
        ),
    }
    contexts: list[dict[str, str]] = []

    async def _read(
        _site_id: str,
        _search_name: str,
        stated: Mapping[str, JsonValue] | None,
        *,
        about: ResolveContext | None,
        record_type: str | None = None,
        bound: Mapping[str, ParamValue],
    ) -> BoundValues:
        del record_type

        async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
            contexts.append(context)
            organism = context.get(
                "organismSinglePick", '["Plasmodium falciparum 3D7"]'
            )
            return list(under[organism].parameters or [])

        return await read_under_parents(
            fetch_at, stated or {}, NoFilterReads(), about=about, bound=bound
        )

    monkeypatch.setattr(_stated_values, "read_stated_parameters", _read)
    return contexts


def _snps_plan(organism: str) -> ProposedReadingDraft:
    return ProposedReadingDraft.model_validate(
        {
            "title": "SNPs in the Peru isolates",
            "searches": [
                {
                    "label": "snps",
                    "searchName": "GenesByNgsSnps",
                    "parameters": {
                        "organismSinglePick": [organism],
                        "variation_sample_meta": [
                            {"field": "Dataset", "value": [_PERU]}
                        ],
                    },
                }
            ],
        }
    )


class TestADependentFilterReadsUnderItsOrganism:
    async def test_the_facet_is_read_under_the_stated_organism(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_recorded_readings(monkeypatch)
        contexts = _snps_under_their_organism(monkeypatch)
        counted = _counted(monkeypatch)

        with pytest.raises(ModelRetry, match=COUNTED):
            await propose_readings(lead_run_context(), [_snps_plan(_VIVAX)])

        [clause] = FilterValue.model_validate(
            counted[0].parameters["variation_sample_meta"].model_dump()
        ).filters
        assert (clause.field, clause.value) == ("VAR_36c1c67a", [_PERU])
        assert {"organismSinglePick": f'["{_VIVAX}"]'}.items() <= contexts[-1].items()

    async def test_a_member_of_another_organism_is_refused_before_any_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_recorded_readings(monkeypatch)
        _snps_under_their_organism(monkeypatch)
        counted = _counted(monkeypatch)

        with pytest.raises(ModelRetry, match="has no member"):
            await propose_readings(
                lead_run_context(), [_snps_plan("Plasmodium falciparum 3D7")]
            )

        assert counted == []


class TestAnOptionsReadReadsItsContext:
    async def test_a_context_value_is_read_under_its_parameter(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        asked: list[Mapping[str, ParamValue] | None] = []

        async def _read(*_args: object, **kwargs: Any) -> object:
            asked.append(kwargs["context_values"])
            raise ModelRetry(READ)

        monkeypatch.setattr(catalog_discovery, "read_parameter_options", _read)
        ctx, _ = context_and_commit(_taxon_graph(), [])

        with pytest.raises(ModelRetry, match="read"):
            await catalog_discovery.get_parameter_options(
                ctx,
                "GenesByNgsSnps",
                "variation_sample_meta",
                context_values={"organismSinglePick": ["Plasmodium vivax P01"]},
            )

        assert asked == [
            {"organismSinglePick": MultiPickValue(values=["Plasmodium vivax P01"])}
        ]

    async def test_a_wrapped_context_value_is_refused_before_the_read(
        self, monkeypatch: pytest.MonkeyPatch, stated_reads: None
    ) -> None:
        asked: list[object] = []

        async def _read(*args: object, **_kwargs: object) -> object:
            asked.append(args)
            return None

        monkeypatch.setattr(catalog_discovery, "read_parameter_options", _read)
        ctx, _ = context_and_commit(_taxon_graph(), [])

        with pytest.raises(ModelRetry, match="organismSinglePick takes a list"):
            await catalog_discovery.get_parameter_options(
                ctx,
                "GenesByNgsSnps",
                "variation_sample_meta",
                context_values={
                    "organismSinglePick": {"type": "string", "value": "P01"}
                },
            )

        assert asked == []


async def test_an_options_read_sends_a_bound_half_open_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    length = _DECLARATION.validate_python(
        {"name": "length", "type": "number-range", "min": 0}
    )
    client = patch_search_details(monkeypatch, parameters=[length, wdk_param("target")])
    ctx, _ = context_and_commit(_taxon_graph(), [])
    ctx.deps.agent_state.frame_set_criterion(
        Criterion(
            id="c1",
            text="long genes",
            search_name="GenesByLength",
            resolved_params=bound({"length": from_wire("number-range", '{"min": 6}')}),
        )
    )

    read = await catalog_discovery.get_parameter_options(ctx, "GenesByLength", "target")

    assert returned(read, ParameterInfo).name == "target"
    assert client.contexts[-1] == {"length": '{"min": 6.0}'}


def test_a_proposed_change_states_each_value_as_json() -> None:
    change = SetValuesChange(
        sentence="Raise the minor allele share.",
        criterion_id="c1",
        params={"MinPercentMinorAlleles": 5},
    )
    added = AddCriterionChange(
        sentence="Add peptides.",
        search_name="GenesWithSignalPeptide",
        params={"organism": [_PF]},
    )

    assert change.binding() == "on criterion c1, set MinPercentMinorAlleles to 5"
    assert added.binding() == (
        f'add a criterion running GenesWithSignalPeptide, organism ["{_PF}"]'
    )
