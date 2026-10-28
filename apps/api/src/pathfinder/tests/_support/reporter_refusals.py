from __future__ import annotations

from collections.abc import Generator

import pytest

from pathfinder.services.experiment.reporter_refusals import REPORTER_REFUSALS


@pytest.fixture(autouse=True)
def _clear_reporter_refusals() -> Generator[None]:
    REPORTER_REFUSALS.clear()
    yield
    REPORTER_REFUSALS.clear()
