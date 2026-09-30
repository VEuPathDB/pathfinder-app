"""The lineup's invariants: one smallest and one default per provider, and the
flags and prices each entry records."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, time
from typing import cast

import pytest
from assistant_core.cost import cost_for_run
from assistant_core.platform.types import ModelProvider
from assistant_core.pricing import lookup_per_mtok_prices
from pydantic_ai.usage import RunUsage

from pathfinder.platform.model_catalog import (
    DEFAULT_MODEL_ID,
    PRICES_AS_OF,
    ModelEntry,
    get_model_catalog,
    get_model_entry,
    get_smallest_model,
    provider_default,
    validate_lineup,
)

_CLOUD: tuple[ModelProvider, ...] = ("openai", "anthropic", "google")


def test_every_provider_has_exactly_one_small_entry() -> None:
    counts = Counter(e.provider for e in get_model_catalog() if e.rank == "small")

    assert {p: counts[p] for p in (*_CLOUD, "mock")} == {
        "openai": 1,
        "anthropic": 1,
        "google": 1,
        "mock": 1,
    }


def test_every_cloud_provider_has_exactly_one_default_entry() -> None:
    counts = Counter(e.provider for e in get_model_catalog() if e.is_provider_default)

    assert {p: counts[p] for p in _CLOUD} == {"openai": 1, "anthropic": 1, "google": 1}


def _lineup(*specs: tuple[str, str, bool]) -> tuple[ModelEntry, ...]:
    return tuple(
        ModelEntry.entry(
            id=f"openai:{name}", name=name, rank=rank, is_provider_default=d
        )
        for name, rank, d in specs
    )


def test_a_lineup_with_one_default_and_one_small_entry_is_kept() -> None:
    lineup = _lineup(("big", "flagship", False), ("tiny", "small", True))

    assert validate_lineup(lineup) == lineup


@pytest.mark.parametrize(
    ("specs", "rule"),
    [
        ((("a", "standard", False), ("b", "small", False)), "0 default"),
        ((("a", "standard", True), ("b", "small", True)), "2 default"),
        ((("a", "standard", True),), "0 small"),
        (
            (("a", "standard", True), ("b", "standard", False), ("c", "small", False)),
            "rank 'standard' twice",
        ),
    ],
)
def test_a_lineup_that_breaks_a_rule_is_refused(
    specs: tuple[tuple[str, str, bool], ...], rule: str
) -> None:
    with pytest.raises(ValueError, match=rule):
        validate_lineup(_lineup(*specs))


def test_the_default_model_is_the_openai_default_entry() -> None:
    assert provider_default("openai").id == DEFAULT_MODEL_ID
    assert DEFAULT_MODEL_ID == "openai:gpt-5.6-luna"


def test_the_lineup_names_the_decided_ids_and_ranks() -> None:
    lineup = {e.id: e.rank for e in get_model_catalog() if e.provider in _CLOUD}

    assert lineup == {
        "openai:gpt-6-sol": "flagship",
        "openai:gpt-6-luna": "small",
        "openai:gpt-5.6-luna": "standard",
        "anthropic:claude-haiku-4-5": "small",
        "google:gemini-3.1-pro-preview": "flagship",
        "google:gemini-3.8-flash": "standard",
        "google:gemini-3.5-flash-lite": "small",
    }


@pytest.mark.parametrize(
    ("model_id", "prices"),
    [
        ("openai:gpt-6-sol", (2.00, 0.20, 10.00)),
        ("openai:gpt-6-luna", (0.10, 0.01, 0.50)),
        ("openai:gpt-5.6-luna", (0.20, 0.02, 1.20)),
        ("anthropic:claude-haiku-4-5", (1.00, 0.10, 5.00)),
        ("google:gemini-3.1-pro-preview", (2.00, 0.20, 12.00)),
        ("google:gemini-3.8-flash", (0.75, 0.075, 3.75)),
        ("google:gemini-3.5-flash-lite", (0.30, 0.03, 2.50)),
    ],
)
def test_an_entry_records_the_price_its_provider_publishes(
    model_id: str, prices: tuple[float, float, float]
) -> None:
    entry = get_model_entry(model_id)

    assert entry is not None
    assert (entry.input_price, entry.cached_input_price, entry.output_price) == prices


@pytest.mark.parametrize(
    "entry",
    [e for e in get_model_catalog() if e.provider in _CLOUD],
    ids=lambda e: e.id,
)
def test_the_price_snapshot_meters_every_cloud_entry(entry: ModelEntry) -> None:
    """A model the snapshot does not know costs nothing in the spend meter."""
    snapshot = lookup_per_mtok_prices(
        entry.provider,
        entry.model_name,
        at=datetime.combine(PRICES_AS_OF, time(12), UTC),
    )

    assert (snapshot.input_, snapshot.output) == (
        entry.input_price,
        entry.output_price,
    )


@pytest.mark.parametrize(
    "entry",
    [e for e in get_model_catalog() if e.provider in _CLOUD],
    ids=lambda e: e.id,
)
def test_the_spend_meter_charges_a_run_on_every_cloud_entry(entry: ModelEntry) -> None:
    """1000 input and 100 output tokens cost a non-zero amount at today's price."""
    snapshot = lookup_per_mtok_prices(entry.provider, entry.model_name)
    cost = cost_for_run(
        usage=RunUsage(input_tokens=1000, output_tokens=100),
        model_name=entry.model_name,
        provider_name=entry.provider,
        provider_url=None,
    )

    assert snapshot.input_ is not None
    assert snapshot.output is not None
    expected = (1000 * snapshot.input_ + 100 * snapshot.output) / 1_000_000
    assert expected > 0
    assert float(cost) == pytest.approx(expected)


@pytest.mark.parametrize("provider", _CLOUD)
def test_get_smallest_model_returns_the_small_entry(provider: ModelProvider) -> None:
    entry = get_smallest_model(provider)

    assert (entry.provider, entry.rank) == (provider, "small")


def test_the_title_the_compactor_and_the_key_check_run_on_the_decided_small_entries() -> (
    None
):
    assert {p: get_smallest_model(p).id for p in _CLOUD} == {
        "openai": "openai:gpt-6-luna",
        "anthropic": "anthropic:claude-haiku-4-5",
        "google": "google:gemini-3.5-flash-lite",
    }


def test_get_smallest_model_raises_for_unknown_provider() -> None:
    # The literal type admits no unknown provider, so the cast names one.
    bogus_provider = cast("ModelProvider", "nonexistent")
    with pytest.raises(LookupError):
        get_smallest_model(bogus_provider)


def test_provider_default_raises_for_a_provider_without_one() -> None:
    with pytest.raises(LookupError):
        provider_default("mock")


# The measured answer of each provider to one 1x1 PNG and one one-page PDF
# (docs/knowledge/decisions/an-attachment-is-a-file-part-the-model-can-read.md).
_READS_FILES = {"openai": True, "google": True, "anthropic": False}


@pytest.mark.parametrize(
    "entry",
    [e for e in get_model_catalog() if e.provider in _READS_FILES],
    ids=lambda e: e.id,
)
def test_a_cloud_model_reads_the_files_its_provider_was_measured_to_read(
    entry: ModelEntry,
) -> None:
    expected = _READS_FILES[entry.provider]
    assert (entry.supports_images, entry.supports_documents) == (expected, expected)


def test_the_mock_reads_no_file() -> None:
    mock = get_model_entry("mock:deterministic")
    assert mock is not None
    assert (mock.supports_images, mock.supports_documents) == (False, False)
