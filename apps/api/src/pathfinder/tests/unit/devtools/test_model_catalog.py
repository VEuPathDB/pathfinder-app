"""The refresh check reads each provider's recorded model list against the catalog."""

from __future__ import annotations

import json

import pytest
from pydantic import JsonValue, SecretStr
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    BinaryContent,
    BinaryImage,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.devtools import model_catalog
from pathfinder.devtools.model_catalog import (
    FIXTURE_DIR,
    CatalogDrift,
    check,
    compare,
    one_pixel_png,
    one_word_pdf,
    parse_page,
    probe,
    render,
)
from pathfinder.domain.provider_keys import KeyableProvider
from pathfinder.platform.model_catalog import (
    PRICES_AS_OF,
    ModelEntry,
    get_model_catalog,
)
from pathfinder.tests._support.models import DEFAULT_MODEL


def _served(provider: KeyableProvider) -> list[str]:
    body = json.loads((FIXTURE_DIR / f"{provider}.json").read_text())
    return parse_page(provider, body).ids()


def test_the_openai_list_reads_every_model_id() -> None:
    served = _served("openai")

    assert {"gpt-6-sol", "gpt-6-luna", "gpt-5.6-luna", "gpt-6-astra"} <= set(served)
    assert not [i for i in served if i.startswith("ft:")]


def test_the_anthropic_list_serves_haiku_under_a_dated_snapshot() -> None:
    served = _served("anthropic")

    assert "claude-haiku-4-5-20251001" in served
    assert "claude-haiku-4-5" not in served


def test_the_google_list_keeps_generation_models_without_the_prefix() -> None:
    served = _served("google")

    assert {"gemini-3.8-flash", "gemini-3.1-pro-preview"} <= set(served)
    assert "gemini-embedding-001" not in served
    assert not [i for i in served if i.startswith("models/")]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
def test_the_catalog_names_only_served_models(provider: KeyableProvider) -> None:
    drift = compare(get_model_catalog(), provider, _served(provider))

    assert drift.not_served == []


def test_served_models_of_a_catalog_family_are_reported() -> None:
    """Every served ``gpt-*`` at or above the catalog's lowest version is named."""
    catalog = (ModelEntry.entry(id="openai:gpt-6-luna", name="Luna", rank="small"),)

    drift = compare(catalog, "openai", _served("openai"))

    assert drift.not_in_catalog == ["gpt-6-astra", "gpt-6-sol"]


def test_a_snapshot_of_a_catalog_alias_is_not_reported_as_new() -> None:
    catalog = (
        ModelEntry.entry(id="anthropic:claude-haiku-4-5", name="Haiku", rank="small"),
    )

    drift = compare(catalog, "anthropic", _served("anthropic"))

    assert drift.not_served == []
    assert "claude-haiku-4-5" not in drift.not_in_catalog
    assert "claude-sonnet-4-5" in drift.not_in_catalog


def test_a_model_the_provider_stopped_serving_is_reported() -> None:
    catalog = (
        ModelEntry.entry(id="openai:gpt-6-retired", name="Retired", rank="small"),
    )

    drift = compare(catalog, "openai", _served("openai"))

    assert drift.not_served == ["gpt-6-retired"]


def test_the_report_names_each_section_and_the_price_date() -> None:
    drift = CatalogDrift(
        provider="openai", not_served=["gpt-6-retired"], not_in_catalog=[]
    )

    assert render([drift], ["google"]).splitlines() == [
        "openai:",
        "  not served: gpt-6-retired",
        "  served, not in the catalog: (none)",
        "google: no deployment key, skipped",
        f"prices as of {PRICES_AS_OF.isoformat()}",
    ]


def test_the_probe_files_are_a_png_and_a_one_page_pdf() -> None:
    png = one_pixel_png()
    pdf = one_word_pdf("READY")

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png.endswith(b"IEND\xaeB`\x82")
    assert pdf.startswith(b"%PDF-1.4\n")
    assert b"(READY) Tj" in pdf
    assert pdf.rstrip().endswith(b"%%EOF")


def _reader(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Answers the probe the way a model that reads both kinds answers it."""
    del info
    request = messages[-1]
    assert isinstance(request, ModelRequest)
    part = request.parts[0]
    assert isinstance(part, UserPromptPart)
    content = list(part.content)
    if any(isinstance(c, BinaryImage) for c in content):
        return ModelResponse(parts=[TextPart("Red.")])
    if any(isinstance(c, BinaryContent) for c in content):
        return ModelResponse(parts=[TextPart("PATHFINDER")])
    return ModelResponse(parts=[TextPart("ready")])


async def test_a_model_that_reads_both_kinds_measures_both_flags() -> None:
    result = await probe(FunctionModel(_reader), DEFAULT_MODEL, "openai")

    assert (result.ready.status, result.ready.text) == (200, "ready")
    assert (result.reads_images, result.reads_documents) == (True, True)


def _blind(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    request = messages[-1]
    assert isinstance(request, ModelRequest)
    part = request.parts[0]
    assert isinstance(part, UserPromptPart)
    if len(list(part.content)) > 1:
        raise ModelHTTPError(400, "blind", body={"error": {"type": "invalid"}})
    return ModelResponse(parts=[TextPart("ready")])


async def test_a_refused_file_measures_the_flag_false() -> None:
    result = await probe(FunctionModel(_blind), DEFAULT_MODEL, "openai")

    assert (result.image.status, result.document.status) == (400, 400)
    assert (result.reads_images, result.reads_documents) == (False, False)


def _recorded(monkeypatch: pytest.MonkeyPatch, catalog: tuple[ModelEntry, ...]) -> None:
    async def pages(provider: KeyableProvider, key: SecretStr) -> list[JsonValue]:
        del key
        body: JsonValue = json.loads((FIXTURE_DIR / f"{provider}.json").read_text())
        return [body]

    monkeypatch.setattr(model_catalog, "fetch_pages", pages)
    monkeypatch.setattr(model_catalog, "_deployment_key", lambda _: SecretStr("k"))
    monkeypatch.setattr(model_catalog, "get_model_catalog", lambda: catalog)


async def test_the_check_fails_when_the_catalog_names_a_model_no_longer_served(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    retired = ModelEntry.entry(id="openai:gpt-6-retired", name="Retired", rank="small")
    _recorded(monkeypatch, (*get_model_catalog(), retired))

    assert await check() == 1
    assert "  not served: gpt-6-retired" in capsys.readouterr().out.splitlines()


async def test_the_check_passes_on_the_catalog_the_providers_serve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _recorded(monkeypatch, get_model_catalog())

    assert await check() == 0
