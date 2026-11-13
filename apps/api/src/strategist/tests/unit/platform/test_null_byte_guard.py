import json

import pytest

from strategist.platform.security import _body_carries_null

_NUL = chr(0)


def _body(payload: object) -> bytes:
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"name": "a" + _NUL + "b"}, id="top-level-value"),
        pytest.param({"outer": {"inner": _NUL}}, id="nested-dict"),
        pytest.param({"ids": ["ok", "bad" + _NUL]}, id="inside-list"),
        pytest.param({"deep": [{"k": [{"j": _NUL}]}]}, id="list-of-dicts"),
        pytest.param({"a" + _NUL: "value"}, id="in-a-key"),
        pytest.param([_NUL], id="top-level-list"),
        pytest.param(_NUL, id="bare-string"),
    ],
)
def test_a_nul_anywhere_in_the_body_is_found(payload: object) -> None:
    assert _body_carries_null(_body(payload)) is True


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"name": "ordinary"}, id="plain-text"),
        pytest.param({"name": "back" + chr(92) + chr(92) + "u0000slash"}, id="escaped"),
        pytest.param({"name": "u0000"}, id="looks-like-an-escape"),
        pytest.param({"count": 0, "flag": False, "nothing": None}, id="non-strings"),
        pytest.param({"unicode": "P. falciparum é中"}, id="other-unicode"),
    ],
)
def test_legitimate_bodies_pass_through(payload: object) -> None:
    assert _body_carries_null(_body(payload)) is False


def test_malformed_json_is_left_for_the_route_to_reject() -> None:
    # Returning True here would answer 422 "null characters" for a body whose
    # real problem is that it is not JSON at all.
    assert _body_carries_null(b"{not json" + _NUL.encode()) is False
