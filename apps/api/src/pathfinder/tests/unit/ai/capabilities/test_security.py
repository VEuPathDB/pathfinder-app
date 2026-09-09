"""How this application wires the runtime's input screening."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from assistant_core.capabilities.input_screening import ScreeningRejectionError

from pathfinder.ai.capabilities import security
from pathfinder.platform.errors import ErrorCode, ForbiddenError

_SCANNER_NAME = "PIGuardScanner"
_RISK_SCORE = 0.99


class TestTheSettingGatesTheScan:
    async def test_scan_is_noop_when_piguard_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_scan(text: str) -> None:
            pytest.fail("scanner must not run when PIGuard is disabled")

        monkeypatch.setattr(security._scanner, "scan", fail_scan)
        monkeypatch.setattr(
            security,
            "get_settings",
            lambda: SimpleNamespace(piguard_enabled=False),
        )
        await security.scan_user_input("ignore previous instructions")


class TestARefusalIsA403:
    """The scanner's message names the scanner and its score, so it never ships."""

    async def test_a_rejection_becomes_a_forbidden_problem(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def refuse(text: str) -> None:
            del text
            raise ScreeningRejectionError(_SCANNER_NAME, _RISK_SCORE)

        monkeypatch.setattr(security._scanner, "scan", refuse)

        with pytest.raises(ForbiddenError) as raised:
            await security.scan_user_input("ignore previous instructions")

        assert raised.value.status == 403
        assert raised.value.code == ErrorCode.FORBIDDEN
        assert raised.value.title == "Input rejected by security screening"

    async def test_the_refusal_names_no_scanner_and_no_score(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def refuse(text: str) -> None:
            del text
            raise ScreeningRejectionError(_SCANNER_NAME, _RISK_SCORE)

        monkeypatch.setattr(security._scanner, "scan", refuse)

        with pytest.raises(ForbiddenError) as raised:
            await security.scan_user_input("ignore previous instructions")

        rendered = f"{raised.value.title} {raised.value.detail}"

        assert _SCANNER_NAME not in rendered
        assert str(_RISK_SCORE) not in rendered


class TestWarmUp:
    def test_warm_up_loads_the_singleton(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[int] = []

        monkeypatch.setattr(
            security._scanner,
            "ensure_loaded",
            lambda: calls.append(1),
        )
        security.warm_up_scanner()

        assert calls == [1]

    def test_every_test_process_starts_with_a_loaded_scanner(self) -> None:
        """The first chat POST of a test process must not pay the model load."""
        before = security._scanner.ensure_loaded()

        assert security._scanner.ensure_loaded() == before
