"""A run whose site login does not answer ends on one line that names the site
and the failure, with exit code 2 and no traceback."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pathfinder.devtools import chat

_ATTEMPTS: list[str] = []


async def _no_answer(site_id: str, email: str, password: str) -> str | None:
    del email, password
    _ATTEMPTS.append(site_id)
    msg = f"{site_id} did not accept the connection"
    raise httpx.ConnectTimeout(msg)


def test_a_login_the_site_does_not_answer_exits_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(chat, "password_login", _no_answer)
    monkeypatch.setattr(chat, "LOGIN_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(chat, "route_framework_logs_to_stderr", lambda: None)
    _ATTEMPTS.clear()
    monkeypatch.setattr(
        "sys.argv",
        [
            "chat",
            "run",
            "hi",
            "--site",
            "cryptodb",
            "--run-dir",
            str(tmp_path / "turn"),
            "--email",
            "researcher@example.org",
            "--password",
            "unused",
        ],
    )

    with pytest.raises(SystemExit) as exited:
        chat.main()

    lines = capsys.readouterr().err.splitlines()
    assert exited.value.code == 2
    assert len(lines) == 1
    assert lines[0].endswith("cryptodb login did not answer (connect timeout)")
    assert _ATTEMPTS == ["cryptodb", "cryptodb"]
    assert not (tmp_path / "turn").exists()


async def test_the_failure_names_the_transport_error_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat, "LOGIN_RETRY_SECONDS", 0.0)

    async def _read_timeout(site_id: str, email: str, password: str) -> str | None:
        del site_id, email, password
        msg = "no response"
        raise httpx.ReadTimeout(msg)

    args = chat.parse_run_args(
        ["hi", "--site", "toxodb", "--email", "a@example.org", "--password", "x"]
    )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(chat, "password_login", _read_timeout)
        with pytest.raises(chat.LoginUnansweredError) as failed:
            await chat._optional_wdk_token(args)

    assert str(failed.value) == "toxodb login did not answer (read timeout)"
