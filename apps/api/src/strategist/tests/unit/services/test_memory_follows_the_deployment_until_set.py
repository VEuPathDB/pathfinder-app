from __future__ import annotations

import pytest

from strategist.platform.config import Settings
from strategist.services.memory_setting import memory_is_on


@pytest.mark.parametrize(
    ("stored", "on_by_default", "expected"),
    [
        (None, False, False),
        (None, True, True),
        (True, False, True),
        (False, True, False),
    ],
)
def test_an_unset_account_follows_the_deployment(
    stored: bool | None, on_by_default: bool, expected: bool
) -> None:
    assert memory_is_on(stored=stored, on_by_default=on_by_default) is expected


def test_the_deployment_keeps_memory_off_unless_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MEMORY_ON_BY_DEFAULT", raising=False)

    assert Settings().memory_on_by_default is False
