"""Fixtures the whole integration tier shares."""

from __future__ import annotations

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session", autouse=True)
def settled_database(postgres_container: PostgresContainer | None) -> None:
    """Settle ``DATABASE_URL`` before the first test of the tier.

    A test that reaches the database through a service, and so requests no
    database fixture of its own, otherwise connects to whatever holds the port.
    """
    del postgres_container
