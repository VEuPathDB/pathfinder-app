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
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import ValidatedParams

from strategist.services.strategies import commit_tree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests.unit.services.strategies._counting_strategy_api import (
    CountingStrategyAPI,
)


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


async def test_a_seed_holding_a_branch_term_pushes_its_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = CountingStrategyAPI()
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr(commit_tree, "validate_parameters", _validate)
    list_every_search_under(monkeypatch, "transcript")
    seed = StrategyStepNode(
        id="step_seed",
        search_name="GenesByMolecularWeight",
        parameters={"organism": MultiPickValue(values=["Haemoproteidae"])},
    )

    await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(seed),
        root_id=seed.id,
        old=None,
        sync_state=WDKSyncState(),
        target=commit_tree.CommitTarget(name="seed", description="", role="internal"),
    )

    assert [c.kwargs["parameters"] for c in api.named("create_step")] == [
        {"organism": json.dumps(["Haemoproteus tartakovskyi strain SISKIN1"])}
    ]
