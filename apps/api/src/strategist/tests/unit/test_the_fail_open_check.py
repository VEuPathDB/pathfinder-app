from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).parents[4] / "scripts" / "check_fail_open.py"
_PATH = "services/sample.py"


def _check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_fail_open", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failures(source: str, allowlist: str = "") -> list[str]:
    check = _check()
    found = check.scan_source(source, _PATH)
    failures: list[str] = check.violations(found, check.read_allowlist(allowlist))
    return failures


def _handled(*body: str) -> str:
    lines = "\n".join(f"        {line}" for line in body)
    return (
        "def read(site):\n"
        "    try:\n"
        "        return fetch(site)\n"
        f"    except OSError:\n{lines}\n"
    )


@pytest.mark.parametrize(
    ("body", "shape"),
    [
        (("return []",), "returns or assigns an empty value"),
        (("return None",), "returns or assigns an empty value"),
        (("return",), "returns or assigns an empty value"),
        (("counts = {}",), "returns or assigns an empty value"),
        (("return with_summary([], 'none')",), "returns or assigns an empty value"),
        (("return set()",), "returns or assigns an empty value"),
        (("pass",), "ends in pass"),
        (("logger.warning('unread')",), "only logs"),
    ],
)
def test_a_handler_that_turns_a_failure_into_a_value_fails(
    body: tuple[str, ...], shape: str
) -> None:
    assert _failures(_handled(*body)) == [f"{_PATH}:read:1 (line 4): {shape}"]


def test_a_loop_handler_that_continues_fails() -> None:
    source = (
        "def read_all(sites):\n"
        "    for site in sites:\n"
        "        try:\n"
        "            fetch(site)\n"
        "        except OSError:\n"
        "            continue\n"
    )

    assert _failures(source) == [f"{_PATH}:read_all:1 (line 5): ends in continue"]


def test_a_handler_that_raises_or_returns_a_typed_unknown_passes() -> None:
    raising = _handled("logger.warning('unread')", "raise SiteDown() from None")
    unread = _handled("return Unread(reason='the site did not answer')")

    assert (_failures(raising), _failures(unread)) == ([], [])


def test_an_allowlisted_handler_passes() -> None:
    allowlist = f"{_PATH}:read:1 the caller reads None as unread (test_x)\n"

    assert _failures(_handled("return None"), allowlist) == []


def test_a_second_handler_in_an_allowlisted_function_is_a_new_key() -> None:
    source = (
        "def read(site):\n"
        "    try:\n"
        "        fetch(site)\n"
        "    except OSError:\n"
        "        return None\n"
        "    try:\n"
        "        parse(site)\n"
        "    except ValueError:\n"
        "        return None\n"
    )
    allowlist = f"{_PATH}:read:1 the caller reads None as unread (test_x)\n"

    assert _failures(source, allowlist) == [
        f"{_PATH}:read:2 (line 8): returns or assigns an empty value"
    ]


def test_a_method_is_keyed_by_its_class() -> None:
    source = (
        "class Reader:\n"
        "    def read(self):\n"
        "        try:\n"
        "            fetch()\n"
        "        except OSError:\n"
        "            pass\n"
    )

    assert _failures(source) == [f"{_PATH}:Reader.read:1 (line 5): ends in pass"]


def test_an_allowlist_line_with_no_handler_fails() -> None:
    allowlist = f"{_PATH}:gone:1 the caller reads None as unread (test_x)\n"

    assert _failures("x = 1\n", allowlist) == [
        f"{_PATH}:gone:1: allowlisted, but no such handler"
    ]


def test_an_allowlist_line_without_a_reason_is_refused() -> None:
    with pytest.raises(ValueError, match="states its reason"):
        _check().read_allowlist(f"{_PATH}:read:1\n")
