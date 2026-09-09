"""The model catalog resolves through the runtime's settings builder."""

from __future__ import annotations

from assistant_core.models.settings import build_model_settings

from pathfinder.ai.models.catalog import get_model_catalog


class TestEveryCatalogEntryResolvesToSettings:
    """Every entry the catalog offers builds settings that keep the timeout."""

    def test_every_entry_carries_the_request_timeout(self) -> None:
        for entry in get_model_catalog():
            assert build_model_settings(entry.id)["timeout"] == 900, entry.id

    def test_every_entry_keeps_its_timeout_under_every_effort(self) -> None:
        for entry in get_model_catalog():
            for effort in ("none", "low", "medium", "high"):
                settings = build_model_settings(entry.id, thinking=effort)

                assert settings["timeout"] == 900, (entry.id, effort)
