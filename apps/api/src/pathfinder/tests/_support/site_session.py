import os
from collections.abc import Generator

import pytest
from veupathdb.testing import NO_CREDENTIALS_REASON, registered_wdk_token

from pathfinder.platform.stage_sites import (
    SITES_CONFIG_VARIABLE,
    use_sites_file,
)


@pytest.fixture(scope="session")
async def wdk_registered_token() -> str | None:
    """The WDK token of the registered test account, or None when unconfigured.

    Resolved once for the whole session.
    """
    return await registered_wdk_token()


@pytest.fixture
def require_wdk_creds(wdk_registered_token: str | None) -> str:
    """The registered WDK token, or a skip naming the credentials to set."""
    if wdk_registered_token is None:
        pytest.skip(NO_CREDENTIALS_REASON)
    return wdk_registered_token


@pytest.fixture
def restored_sites_file() -> Generator[None]:
    previous = os.environ.get(SITES_CONFIG_VARIABLE)
    yield
    use_sites_file(previous)
