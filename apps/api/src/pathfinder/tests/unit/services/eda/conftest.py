from __future__ import annotations

import pytest

from pathfinder.tests._support.eda_subset_search_doubles import (
    serve_plasmodb_subset_searches,
)


@pytest.fixture(autouse=True)
def plasmodb_subset_searches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return serve_plasmodb_subset_searches(monkeypatch)
