"""The suite runs on the test profile whatever the host environment says."""

from __future__ import annotations

import os


def test_the_suite_runs_on_the_mock_provider() -> None:
    assert os.environ["PATHFINDER_CHAT_PROVIDER"] == "mock"


def test_the_suite_runs_in_the_test_environment() -> None:
    assert os.environ["API_ENV"] == "test"


def test_the_suite_screens_input_by_default() -> None:
    assert os.environ["INPUT_SCREENING_ENABLED"] == "true"
