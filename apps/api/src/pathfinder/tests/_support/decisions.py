from __future__ import annotations

from collections.abc import Iterator

import pytest
from veupathdb_mcp.catalog import post_decision, use_decisions_transport
from veupathdb_mcp.testing import offline_decisions

OFFLINE_OPENAI_KEY = "sk-offline-test-key"


@pytest.fixture(autouse=True)
def answer_no_decisions() -> Iterator[None]:
    use_decisions_transport(offline_decisions)
    yield
    use_decisions_transport(post_decision)
