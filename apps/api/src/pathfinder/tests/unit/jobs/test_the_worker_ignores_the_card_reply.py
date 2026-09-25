"""A durable card call forwards its reply to the job, and the worker reads none of it."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from pathfinder.jobs.impls.optimize_params_impl import optimize_search_parameters_impl
from pathfinder.jobs.impls.separate_controls_impl import separate_controls_impl


@pytest.mark.parametrize(
    "impl", [optimize_search_parameters_impl, separate_controls_impl]
)
def test_the_reply_lands_in_the_ignored_keywords(impl: Callable[..., Any]) -> None:
    parameters = inspect.signature(impl).parameters

    assert "reply" not in parameters
    assert [p.name for p in parameters.values() if p.kind is p.VAR_KEYWORD] == [
        "_extra"
    ]
