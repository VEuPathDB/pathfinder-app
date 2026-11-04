from __future__ import annotations

import pytest
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk import WDKUserInfo

from pathfinder.platform.errors import SiteUnavailableError
from pathfinder.services.audit import sign_in
from pathfinder.services.audit.sign_in import sign_in_check

_REGISTERED = WDKUserInfo.model_validate(
    {"id": 1, "email": "reader@example.org", "isGuest": False}
)
_GUEST = WDKUserInfo.model_validate({"id": 2, "isGuest": True})


def _token_reads_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _valid() -> None:
        return None

    monkeypatch.setattr(sign_in, "require_registered_wdk_login", _valid)


def _site_answers(
    monkeypatch: pytest.MonkeyPatch, answer: WDKUserInfo | Exception | None
) -> list[str]:
    asked: list[str] = []

    async def _read(site_id: str) -> WDKUserInfo | None:
        asked.append(site_id)
        match answer:
            case Exception():
                raise answer
            case _:
                return answer

    monkeypatch.setattr(sign_in, "current_user_on_a_site_that_answers", _read)
    return asked


async def test_a_sign_in_the_site_names_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    _token_reads_valid(monkeypatch)
    asked = _site_answers(monkeypatch, _REGISTERED)
    assert await sign_in_check("plasmodb") == "held"
    assert asked == ["plasmodb"]


@pytest.mark.parametrize("answer", [None, _GUEST])
async def test_a_valid_token_the_site_refuses_is_refused(
    monkeypatch: pytest.MonkeyPatch, answer: WDKUserInfo | None
) -> None:
    _token_reads_valid(monkeypatch)
    _site_answers(monkeypatch, answer)
    assert await sign_in_check("plasmodb") == "refused"


async def test_a_site_that_does_not_answer_leaves_the_check_unanswered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _token_reads_valid(monkeypatch)
    _site_answers(monkeypatch, SiteUnavailableError("plasmodb", "timed out"))
    assert await sign_in_check("plasmodb") == "unanswered"


async def test_a_token_refused_locally_asks_no_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refused() -> None:
        raise WDKLoginRequiredError

    monkeypatch.setattr(sign_in, "require_registered_wdk_login", _refused)
    asked = _site_answers(monkeypatch, _REGISTERED)
    assert await sign_in_check("plasmodb") == "refused"
    assert asked == []
