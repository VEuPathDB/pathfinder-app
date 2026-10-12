from collections.abc import Generator

import pytest
from veupathdb.guest_token import guest_tokens, use_guest_tokens
from veupathdb.testing import hermetic_guest_tokens


@pytest.fixture(autouse=True)
def _hermetic_guest(request: pytest.FixtureRequest) -> Generator[None]:
    if request.node.get_closest_marker("live_wdk") is not None:
        yield
        return
    previous = guest_tokens()
    use_guest_tokens(hermetic_guest_tokens())
    yield
    use_guest_tokens(previous)
