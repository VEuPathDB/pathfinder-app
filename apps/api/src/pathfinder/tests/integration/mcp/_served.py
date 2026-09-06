"""The served veupathdb-wdk-mcp endpoint, the credentials it admits, and one step.

Shared by every credentialed test of the served server, so that the endpoint and
the account under test are named in one place.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel
from pydantic_ai.mcp import MCPToolset
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters.values import MultiPickValue, NumberValue, ParamValue
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.strategy_api import StrategyAPI
from veupathdb.wdk.value_decoding import encode_params
from veupathdb.wdk.wdk_models import (
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
)

SITE = "plasmodb"
RECORD_TYPE = "transcript"
ORGANISM = "Plasmodium falciparum 3D7"

URL_VARIABLE = "PATHFINDER_MCP_URL"
DEFAULT_URL = "http://localhost:8100/mcp"
SERVICE_TOKENS_VARIABLE = "PATHFINDER_MCP_SERVICE_TOKENS"

# A short budget for the reads, so a hung endpoint fails instead of waiting.
READ_SECONDS = 60.0

TARGET_SEARCH = "GenesByMolecularWeight"
TARGET_PARAMETERS: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=[ORGANISM]),
    "min_molecular_weight": NumberValue(value=10_000),
    "max_molecular_weight": NumberValue(value=20_000),
}


class OwnedStep(BaseModel):
    """A step of the account under test, and the strategy that carries it."""

    strategy_id: int
    step_id: int


def served_url() -> str:
    return os.environ.get(URL_VARIABLE, DEFAULT_URL)


def connect(bearer: str, *, read_seconds: float = READ_SECONDS) -> MCPToolset[None]:
    """A client of the served endpoint, acting as the credential in the bearer."""
    return MCPToolset[None](served_url(), auth=bearer, read_timeout=read_seconds)


def wire(parameters: dict[str, ParamValue]) -> dict[str, Any]:
    """Parameter values in the shape a served tool takes them."""
    return {
        name: value.model_dump(by_alias=True, mode="json")
        for name, value in parameters.items()
    }


async def strategy_ids(api: StrategyAPI) -> set[int]:
    return {item.strategy_id for item in await api.list_strategies()}


@asynccontextmanager
async def owned_step_for(bearer: str) -> AsyncIterator[OwnedStep]:
    """A step of the bearer's account, deleted with its strategy afterwards."""
    reset = veupathdb_auth_token_ctx.set(bearer)
    api = get_strategy_api(SITE)
    step = await api.create_step(
        NewStepSpec(
            searchName=TARGET_SEARCH,
            searchConfig=WDKSearchConfig(parameters=encode_params(TARGET_PARAMETERS)),
        ),
        record_type=RECORD_TYPE,
    )
    strategy = await api.create_strategy(
        WDKStepTree(stepId=step.id),
        name="pathfinder-mcp-live",
        is_internal=True,
    )
    try:
        yield OwnedStep(strategy_id=strategy.id, step_id=step.id)
    finally:
        # WDK deletes a strategy's steps with the strategy.
        await api.delete_strategy(strategy.id)
        veupathdb_auth_token_ctx.reset(reset)
