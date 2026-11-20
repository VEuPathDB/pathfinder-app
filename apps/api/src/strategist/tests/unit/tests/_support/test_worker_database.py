from __future__ import annotations

import pytest

from strategist.tests._support.worker_database import (
    shared_database_url,
    worker_database_url,
    worker_scoped,
)

_SHARED = "postgresql+asyncpg://postgres:postgres@localhost:5432/strategist_test"


def test_a_serial_run_keeps_the_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    assert worker_scoped("strategist_test_three_chains") == (
        "strategist_test_three_chains"
    )
    assert worker_database_url(_SHARED) == _SHARED


def test_a_worker_names_a_database_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")

    assert worker_scoped("strategist_test_three_chains") == (
        "strategist_test_three_chains_gw3"
    )
    assert worker_database_url(_SHARED) == (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/strategist_test_gw3"
    )


def test_two_workers_never_share_a_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    first = worker_database_url(_SHARED)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    second = worker_database_url(_SHARED)

    assert (first, second) == (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/strategist_test_gw0",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/strategist_test_gw1",
    )


def test_a_worker_database_names_the_shared_one_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")

    assert shared_database_url(worker_database_url(_SHARED)) == _SHARED
    assert shared_database_url(_SHARED) == _SHARED


def test_a_serial_run_shares_its_own_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    assert shared_database_url(_SHARED) == _SHARED
