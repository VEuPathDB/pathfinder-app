"""A curated tree is a statement, so a branch it holds is pushed as its leaves."""

from __future__ import annotations

import json
from typing import Any

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParameterCanonicalizer,
    ParamSpecNormalized,
)
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import NewStepSpec, WDKIdentifier, WDKSearchResponse
from veupathdb_mcp.catalog import ValidatedParams

from strategist.services.experiment import materialization
from strategist.tests._support.record_classes import list_every_search_under
from strategist_scripted.seeds.record import materialize_step_tree


def _organism() -> ParamSpecNormalized:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_molecular_weight").json_body()
    ).search_data
    organism = next(p for p in search.parameters or [] if p.name == "organism")
    return ParamSpecNormalized(
        name="organism",
        param_type="multi-pick-vocabulary",
        vocabulary=organism.vocabulary,
        count_only_leaves=True,
    )


async def _validate(*_args: Any, **kwargs: Any) -> ValidatedParams:
    canonical = ParameterCanonicalizer({"organism": _organism()}).canonicalize(
        kwargs["stated"]
    )
    return ValidatedParams(params=canonical, record_class="transcript")


class _Api:
    def __init__(self) -> None:
        self.posted: list[dict[str, str]] = []

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        self.posted.append(dict(spec.search_config.parameters))
        return WDKIdentifier(id=41)


async def test_a_seed_holding_a_branch_term_pushes_its_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api()
    monkeypatch.setattr(materialization, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(materialization, "validate_parameters", _validate)
    list_every_search_under(monkeypatch, "transcript")
    seed = StrategyStepNode(
        id="step_seed",
        search_name="GenesByMolecularWeight",
        parameters={"organism": MultiPickValue(values=["Haemoproteidae"])},
    )

    await materialize_step_tree("plasmodb", seed, [])

    assert api.posted == [
        {"organism": json.dumps(["Haemoproteus tartakovskyi strain SISKIN1"])}
    ]
