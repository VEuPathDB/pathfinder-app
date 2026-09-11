"""Which vocabulary ``get_parameter_options`` answers with: bound parents,
dependent parameters, the clade lists and the organism hints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from veupathdb.domain.parameters.values import SinglePickValue
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParameterNotOnSearch,
    ParentContextRequired,
    search_inspection,
)

from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_state_ctx,
    patch_search_details,
    wdk_param,
)


def _pin_formatter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_inspection,
        "format_typed_param",
        lambda *_a, **_kw: MagicMock(kind="parameter_info"),
    )


def _param_info(**overrides: Any) -> ParameterInfo:
    base: dict[str, Any] = {
        "name": "p",
        "display_name": "P",
        "type": "string",
        "required": True,
        "is_visible": True,
        "help": "",
        "value_format": "",
    }
    base.update(overrides)
    return ParameterInfo.model_validate(base)


class TestInheritsBoundParentContext:
    """A read with no explicit context still sends the parent values the spec
    binds; without them WDK answers from the search defaults."""

    @staticmethod
    def _ctx_with_bound_profileset() -> Any:
        ctx = agent_state_ctx()
        ctx.deps.agent_state.frame_set_criterion(
            Criterion(
                id="timecourse",
                text="trophozoite expression",
                search_name="GenesByMicroarrayDerisi",
                resolved_params={
                    "profileset_generic": SinglePickValue(value="DeRisi 3D7 Smoothed")
                },
            )
        )
        return ctx

    async def test_it_sends_the_bound_parent_to_wdk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = patch_search_details(
            monkeypatch, parameters=[wdk_param("samples_percentile_generic")]
        )
        _pin_formatter(monkeypatch)

        await catalog_discovery.get_parameter_options(
            self._ctx_with_bound_profileset(),
            search_name="GenesByMicroarrayDerisi",
            parameter_id="samples_percentile_generic",
        )

        client.get_search_details_with_params.assert_awaited_once()
        context = client.get_search_details_with_params.await_args.kwargs["context"]
        assert context["profileset_generic"] == "DeRisi 3D7 Smoothed"

    async def test_an_explicit_context_overrides_the_bound_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = patch_search_details(
            monkeypatch, parameters=[wdk_param("samples_percentile_generic")]
        )
        _pin_formatter(monkeypatch)

        await catalog_discovery.get_parameter_options(
            self._ctx_with_bound_profileset(),
            search_name="GenesByMicroarrayDerisi",
            parameter_id="samples_percentile_generic",
            context_values={"profileset_generic": "DeRisi Dd2 Smoothed"},
        )

        context = client.get_search_details_with_params.await_args.kwargs["context"]
        assert context["profileset_generic"] == "DeRisi Dd2 Smoothed"

    async def test_an_unbound_search_still_reads_without_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(monkeypatch, parameters=[wdk_param("go_term")])
        _pin_formatter(monkeypatch)

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(), search_name="GenesByGoTerm", parameter_id="go_term"
            )
        ).return_value

        assert result.kind == "parameter_info"
        assert not isinstance(result, ParameterNotOnSearch)

    async def test_the_inherited_context_reaches_the_formatter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(
            monkeypatch, parameters=[wdk_param("samples_percentile_generic")]
        )
        seen: dict[str, Any] = {}

        def _format(*_a: Any, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return MagicMock(kind="parameter_info")

        monkeypatch.setattr(search_inspection, "format_typed_param", _format)

        await catalog_discovery.get_parameter_options(
            self._ctx_with_bound_profileset(),
            search_name="GenesByMicroarrayDerisi",
            parameter_id="samples_percentile_generic",
        )

        assert seen["applied_context"] == {
            "profileset_generic": SinglePickValue(value="DeRisi 3D7 Smoothed")
        }


def _with_dependency(monkeypatch: pytest.MonkeyPatch, child: str, parent: str) -> None:
    parent_param = wdk_param(parent)
    parent_param.dependent_params = [child]
    patch_search_details(monkeypatch, parameters=[parent_param, wdk_param(child)])


class TestADependentReadNeedsItsParent:
    """The vocabulary differs per parent, so an unqualified read is a guess."""

    async def test_an_unbound_parent_does_not_return_a_term_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_dependency(
            monkeypatch, "samples_percentile_generic", "profileset_generic"
        )

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByProfile",
                parameter_id="samples_percentile_generic",
            )
        ).return_value

        assert isinstance(result, ParentContextRequired)
        assert result.kind == "parent_context_required"
        assert result.parameter_id == "samples_percentile_generic"
        assert result.search_name == "GenesByProfile"

    async def test_it_names_the_parent_to_bind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_dependency(
            monkeypatch, "samples_percentile_generic", "profileset_generic"
        )

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByProfile",
                parameter_id="samples_percentile_generic",
            )
        ).return_value

        assert isinstance(result, ParentContextRequired)
        assert result.parent_parameter_ids == ["profileset_generic"]

    async def test_an_explicit_context_is_answered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _with_dependency(
            monkeypatch, "samples_percentile_generic", "profileset_generic"
        )
        info = MagicMock(kind="parameter_info")
        monkeypatch.setattr(
            search_inspection, "format_typed_param", lambda *_a, **_kw: info
        )

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByProfile",
                parameter_id="samples_percentile_generic",
                context_values={"profileset_generic": "DeRisi 3D7 Smoothed"},
            )
        ).return_value

        assert result is info

    async def test_a_parameter_with_no_parents_is_unaffected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        patch_search_details(monkeypatch, parameters=[wdk_param("organism")])
        info = MagicMock(kind="parameter_info")
        monkeypatch.setattr(
            search_inspection, "format_typed_param", lambda *_a, **_kw: info
        )

        result = (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(), search_name="GenesByTaxon", parameter_id="organism"
            )
        ).return_value

        assert result is info


def _term(code: str, display: str) -> WDKVocabTerm:
    return WDKVocabTerm((code, display, None))


_PHYLETIC_PARAMS: list[WDKParameter] = [
    WDKStringParam(name="profile_pattern", is_visible=False),
    WDKStringParam(
        name="included_species", allow_empty_value=True, initial_display_value=""
    ),
    WDKStringParam(
        name="excluded_species", allow_empty_value=True, initial_display_value=""
    ),
    WDKEnumParam(
        name="phyletic_term_map",
        type="multi-pick-vocabulary",
        vocabulary=[
            _term("ALL", "Root"),
            _term("EUKA", "Eukaryota"),
            _term("MAMM", "Mammalia"),
            _term("hsap", "Homo sapiens REF"),
            _term("pfal", "Plasmodium falciparum 3D7"),
        ],
    ),
    WDKEnumParam(
        name="phyletic_indent_map",
        type="multi-pick-vocabulary",
        vocabulary=[
            _term("EUKA", "1"),
            _term("MAMM", "2"),
            _term("hsap", "3"),
            _term("pfal", "2"),
        ],
    ),
]


class TestReadingOnePhyleticList:
    """A single-parameter read shows the same vocabulary the sheet shows.

    The two lists carry no WDK vocabulary of their own.
    """

    @staticmethod
    async def _read(
        monkeypatch: pytest.MonkeyPatch,
        *,
        parameter_id: str = "included_species",
        query: str | None = None,
    ) -> Any:
        patch_search_details(monkeypatch, parameters=_PHYLETIC_PARAMS)
        return (
            await catalog_discovery.get_parameter_options(
                agent_state_ctx(),
                search_name="GenesByOrthologPattern",
                parameter_id=parameter_id,
                query=query,
            )
        ).return_value

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("homo", [("hsap", "Homo sapiens REF")]),
            ("PFAL", [("pfal", "Plasmodium falciparum 3D7")]),
            ("human", []),
        ],
        ids=["scientific-name", "code", "common-name-matches-nothing"],
    )
    async def test_the_query_filters_over_codes_and_scientific_names(
        self,
        monkeypatch: pytest.MonkeyPatch,
        query: str,
        expected: list[tuple[str, str]],
    ) -> None:
        info = await self._read(monkeypatch, query=query)

        assert isinstance(info, ParameterInfo)
        options = info.allowed_values or []
        assert [(o.value, o.display) for o in options] == expected

    async def test_the_read_carries_the_derivation_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        info = await self._read(monkeypatch, query="homo")

        assert isinstance(info, ParameterInfo)
        assert "profile_pattern is derived from these two lists" in info.help

    async def test_no_query_returns_the_whole_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        info = await self._read(monkeypatch, parameter_id="excluded_species")

        assert isinstance(info, ParameterInfo)
        assert info.allowed_values is not None
        assert [o.value for o in info.allowed_values] == [
            "EUKA",
            "MAMM",
            "hsap",
            "pfal",
        ]

    async def test_the_hidden_pattern_gains_no_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        info = await self._read(monkeypatch, parameter_id="profile_pattern")

        assert isinstance(info, ParameterInfo)
        assert info.name == "profile_pattern"
        assert info.is_visible is False
        assert info.allowed_values is None


class TestTheInvestigationsOrganismsReachTheRead:
    """The tree is capped, so the read is told which organisms matter."""

    async def test_the_hints_are_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        read = AsyncMock(return_value=_param_info(name="ms_assay"))
        monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)
        ctx = agent_state_ctx()
        ctx.deps.agent_state.organism_hints = ["Plasmodium falciparum"]

        await catalog_discovery.get_parameter_options(
            ctx, search_name="GenesByMassSpec", parameter_id="ms_assay"
        )

        assert read.await_args is not None
        narrowing = read.await_args.kwargs["narrowing"]
        assert list(narrowing.organism_hints) == ["Plasmodium falciparum"]

    async def test_no_hints_reads_without_them(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        read = AsyncMock(return_value=_param_info(name="ms_assay"))
        monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)

        await catalog_discovery.get_parameter_options(
            agent_state_ctx(),
            search_name="GenesByMassSpec",
            parameter_id="ms_assay",
        )

        assert read.await_args is not None
        narrowing = read.await_args.kwargs["narrowing"]
        assert list(narrowing.organism_hints) == []
