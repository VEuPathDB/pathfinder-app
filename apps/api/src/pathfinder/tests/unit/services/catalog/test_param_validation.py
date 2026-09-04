"""Validating parameters against WDK: dependent refresh and the errors it carries."""

from __future__ import annotations

from typing import Any, cast

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import JsonValue

from pathfinder.domain.parameters.specs import ParamSpecNormalized
from pathfinder.domain.parameters.values import ParamValue, SinglePickValue
from pathfinder.domain.search import SearchContext
from pathfinder.integrations.veupathdb.wdk_models import WDKSearchResponse
from pathfinder.integrations.veupathdb.wdk_parameters import WDKEnumParam, WDKParameter
from pathfinder.platform.errors import AppError, ErrorCode, ValidationError
from pathfinder.services.catalog import param_validation as pv

from .conftest import validation_callbacks, wdk_search_response

_CTX = SearchContext(
    site_id="plasmodb", record_type="transcript", search_name="GenesByOrganism"
)
_PROFILE_CTX = SearchContext(
    site_id="plasmodb", record_type="transcript", search_name="GenesByProfile"
)
_STATIC_TAXON_VOCAB = [
    ["TaxonA", "Taxon A", None],
    ["TaxonB", "Taxon B", None],
    ["TaxonC", "Taxon C", None],
]
_REFRESHED_TAXON_VOCAB = [["TaxonA", "Taxon A", None]]


def _enum_param(
    name: str,
    *,
    type_: str = "single-pick-vocabulary",
    vocab: list[list[str | None]],
    dependent_params: list[str] | None = None,
    hidden_default: str | None = None,
) -> WDKParameter:
    raw: JSONObject = {
        "type": type_,
        "name": name,
        "display_name": name,
        "vocabulary": cast("JsonValue", vocab),
        "dependent_params": cast("JsonValue", list(dependent_params or [])),
        "allow_empty_value": False,
    }
    if hidden_default is not None:
        raw["is_visible"] = False
        raw["initial_display_value"] = hidden_default
    return cast("WDKParameter", WDKEnumParam.model_validate(raw))


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    response: WDKSearchResponse,
    refresh: Any,
) -> None:
    async def _expand(ctx: SearchContext, raw_context: JSONObject) -> WDKSearchResponse:
        del ctx, raw_context
        return response

    async def _resolve(
        ctx: SearchContext, *, resolved_record_type: str, parameters: JSONObject
    ) -> pv.ResolvedSearch:
        del ctx, resolved_record_type, parameters
        return pv.ResolvedSearch(response=response, values_were_read=True)

    monkeypatch.setattr(pv, "expand_search_details_with_params", _expand)
    monkeypatch.setattr(pv, "_resolve_search_details", _resolve)
    monkeypatch.setattr(pv, "get_refreshed_dependent_params", refresh)


@pytest.fixture
def stub_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    organism = _enum_param(
        "organism",
        vocab=[["Pf3D7", "P. falciparum 3D7", None], ["PvP01", "P. vivax P01", None]],
        dependent_params=["taxon"],
    )
    taxon = _enum_param("taxon", vocab=_STATIC_TAXON_VOCAB)
    refreshed_taxon = _enum_param("taxon", vocab=_REFRESHED_TAXON_VOCAB)

    async def _refresh(
        ctx: SearchContext, *, parameter_name: str, context_values: JSONObject
    ) -> list[WDKParameter]:
        del ctx, context_values
        return [refreshed_taxon] if parameter_name == "organism" else []

    _serve(
        monkeypatch,
        wdk_search_response(
            "GenesByOrganism",
            [organism, taxon],
            level="NONE",
            is_valid=False,
        ),
        _refresh,
    )


class TestTheErrorCarriesThePostRefreshVocabulary:
    async def test_an_invalid_dependent_value_names_the_refreshed_options(
        self, stub_validation: None
    ) -> None:
        del stub_validation
        with pytest.raises(ValidationError) as excinfo:
            await pv.validate_parameters(
                _CTX,
                parameters={
                    "organism": SinglePickValue(value="Pf3D7"),
                    "taxon": SinglePickValue(value="TaxonB"),
                },
                callbacks=validation_callbacks(),
            )

        assert excinfo.value.errors is not None
        entry = cast("dict[str, Any]", excinfo.value.errors[0])
        assert entry["param"] == "taxon"
        assert entry["value"] == "TaxonB"
        assert entry["validOptions"] == ["TaxonA"]

    async def test_a_missing_required_param_serializes_the_refreshed_spec(
        self, stub_validation: None
    ) -> None:
        del stub_validation
        with pytest.raises(ValidationError) as excinfo:
            await pv.validate_parameters(
                _CTX,
                parameters={"organism": SinglePickValue(value="Pf3D7")},
                callbacks=validation_callbacks(),
            )

        assert excinfo.value.errors is not None
        raw_entry = cast("dict[str, Any]", excinfo.value.errors[0])
        context = cast("dict[str, Any]", raw_entry["context"])
        assert context["missing"] == ["taxon"]
        parameters_spec = cast("list[dict[str, Any]]", context["parameters"])
        taxon_spec = next(p for p in parameters_spec if p["name"] == "taxon")
        assert [v["value"] for v in taxon_spec["allowedValues"]] == ["TaxonA"]


class TestAHiddenParentIsFilledBeforeRefresh:
    """A hidden parent's default must be present when its child refreshes.

    ``_refresh_dependent_vocabularies`` skips a parent whose value is empty, so a
    hidden required parent filled after it would leave the child unrefreshed and
    values WDK accepts reported invalid.
    """

    @pytest.fixture
    def refreshed_parents(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        asked: list[str] = []

        async def _refresh(
            ctx: SearchContext, *, parameter_name: str, context_values: JSONObject
        ) -> list[WDKParameter]:
            del ctx, context_values
            asked.append(parameter_name)
            return []

        _serve(
            monkeypatch,
            wdk_search_response(
                "GenesByMicroarray",
                [
                    _enum_param(
                        "channel",
                        vocab=[["Channel 1", "Channel 1", None]],
                        dependent_params=["samples"],
                        hidden_default="Channel 1",
                    ),
                    _enum_param(
                        "samples",
                        type_="multi-pick-vocabulary",
                        vocab=_STATIC_TAXON_VOCAB,
                    ),
                ],
                level="NONE",
                is_valid=False,
            ),
            _refresh,
        )
        return asked

    @staticmethod
    async def _validate() -> pv.ValidatedParams:
        # The caller never mentions `channel`, exactly what the model sends.
        return await pv.validate_parameters(
            SearchContext("plasmodb", "transcript", "GenesByMicroarray"),
            parameters={"samples": SinglePickValue(value="TaxonA")},
            callbacks=validation_callbacks(),
        )

    async def test_the_hidden_parent_triggers_a_refresh(
        self, refreshed_parents: list[str]
    ) -> None:
        await self._validate()

        assert "channel" in refreshed_parents, (
            "a hidden parent with a default must be filled before its child's "
            "vocabulary is refreshed"
        )

    async def test_the_filled_default_reaches_the_result(
        self, refreshed_parents: list[str]
    ) -> None:
        del refreshed_parents

        assert "channel" in (await self._validate()).params


_REFRESHED_SAMPLES = [["7 Hour", "7 Hour", None]]
_STATIC_SAMPLES = [["20 Hour", "20 Hour", None], ["30 Hour", "30 Hour", None]]


def _spec(name: str, *, dependents: tuple[str, ...] = ()) -> ParamSpecNormalized:
    return ParamSpecNormalized(
        name=name, param_type="multi-pick-vocabulary", dependent_params=dependents
    )


def _specs() -> dict[str, ParamSpecNormalized]:
    return {
        "profileset": _spec("profileset", dependents=("samples",)),
        "samples": _spec("samples"),
        "any_or_all": _spec("any_or_all"),
    }


def _answering(
    monkeypatch: pytest.MonkeyPatch, params: list[WDKParameter]
) -> list[str]:
    asked: list[str] = []

    async def _refresh(
        ctx: SearchContext, *, parameter_name: str, context_values: JSONObject
    ) -> list[WDKParameter]:
        del ctx, context_values
        asked.append(parameter_name)
        return params

    monkeypatch.setattr(pv, "get_refreshed_dependent_params", _refresh)
    return asked


async def _refreshed_specs(
    values: dict[str, ParamValue] | None = None,
) -> dict[str, ParamSpecNormalized]:
    return await pv._refresh_dependent_vocabularies(
        ctx=_PROFILE_CTX,
        param_spec_map=_specs(),
        canonical_values=(
            {"profileset": SinglePickValue(value="DeRisi 3D7 Smoothed")}
            if values is None
            else values
        ),
    )


class TestTheRefreshAnswersWithTheStaleDependentsOnly:
    """A parameter that is absent was not asked about. An empty array is neither a
    failure nor a confirmation."""

    async def test_the_returned_dependent_replaces_its_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answering(monkeypatch, [_enum_param("samples", vocab=_REFRESHED_SAMPLES)])

        specs = await _refreshed_specs()

        assert [t.term for t in specs["samples"].vocabulary or []] == ["7 Hour"]

    async def test_only_the_parent_with_dependents_is_asked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _answering(
            monkeypatch, [_enum_param("samples", vocab=_REFRESHED_SAMPLES)]
        )

        await _refreshed_specs()

        assert asked == ["profileset"]

    async def test_an_empty_array_changes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answering(monkeypatch, [])

        assert await _refreshed_specs() == _specs()

    async def test_an_unmentioned_param_keeps_its_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answering(monkeypatch, [_enum_param("samples", vocab=_REFRESHED_SAMPLES)])

        specs = await _refreshed_specs()

        assert specs["any_or_all"] == _spec("any_or_all")

    async def test_a_param_that_is_not_a_declared_dependent_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _answering(monkeypatch, [_enum_param("any_or_all", vocab=_REFRESHED_SAMPLES)])

        specs = await _refreshed_specs()

        assert specs["any_or_all"] == _spec("any_or_all")

    async def test_an_error_does_not_empty_the_specs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _raise(
            ctx: SearchContext, *, parameter_name: str, context_values: JSONObject
        ) -> list[WDKParameter]:
            del ctx, parameter_name, context_values
            raise AppError(code=ErrorCode.WDK_ERROR, title="refresh failed", status=502)

        monkeypatch.setattr(pv, "get_refreshed_dependent_params", _raise)

        assert await _refreshed_specs() == _specs()

    async def test_an_unset_parent_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _answering(monkeypatch, [_enum_param("samples", vocab=_STATIC_SAMPLES)])

        await _refreshed_specs({})

        assert asked == []
