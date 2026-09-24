"""A variable with no histogram is refused in the researcher's words."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaClient, EdaPermissionEntry, EdaStudyDetail
from veupathdb.errors import ValidationError

from pathfinder.services.eda import authoring, catalog
from pathfinder.tests._support.eda_doubles import permission_entry, study_of
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    DE_DATASET,
    TEMPERATURE_VARIABLE,
    de_study,
)
from pathfinder.tests._support.eda_wire import BASE_URL

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def counts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every count answers, so only the histogram is left to refuse."""
    reset = veupathdb_auth_token_ctx.set("t")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"count": 12})

    client = EdaClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(authoring, "get_eda_client", lambda _site: client)
    yield
    veupathdb_auth_token_ctx.reset(reset)


async def _refusal(entity_id: str, variable_id: str) -> ValidationError:
    with pytest.raises(ValidationError) as refusal:
        await authoring.variable_distribution(
            "plasmodb",
            dataset_id=DE_DATASET,
            entity_id=entity_id,
            variable_id=variable_id,
            filters=[],
        )
    assert refusal.value.title == "No distribution for this variable"
    return refusal.value


async def test_a_variable_the_entity_does_not_declare_names_no_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(authoring, "get_study_detail_for_dataset", de_study)

    refusal = await _refusal(COUNTS_ENTITY, TEMPERATURE_VARIABLE)

    assert refusal.detail == "The study declares no such variable on this entity."


async def test_a_continuous_variable_with_no_bin_width_is_named_by_its_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variable = {
        "id": "VAR_hours",
        "type": "number",
        "displayName": "Hours post infection",
        "dataShape": "continuous",
        "distributionDefaults": {"rangeMin": 0, "rangeMax": 48},
    }

    async def hours_study(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        return permission_entry(), study_of([variable], entity_id="E")

    monkeypatch.setattr(authoring, "get_study_detail_for_dataset", hours_study)
    monkeypatch.setattr(catalog, "get_study_detail_for_dataset", hours_study)

    refusal = await _refusal("E", "VAR_hours")

    assert refusal.detail == (
        "Hours post infection is continuous, and a histogram needs a number "
        "variable with a declared bin width."
    )
